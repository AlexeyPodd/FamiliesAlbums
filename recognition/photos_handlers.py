import os
import re

import redis
import pickle
from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos, Albums
from photoalbums.settings import REDIS_HOST, REDIS_PORT, BASE_DIR, REDIS_DATA_EXPIRATION_SECONDS, \
    FACE_RECOGNITION_TOLERANCE, PATTERN_EQUALITY_TOLERANCE, MEDIA_ROOT, CLUSTER_LIMIT, \
    UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT, MINIMAL_CLUSTER_TO_RECALCULATE

from .data_classes import *
from .models import *


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


class FaceSearchingHandler:
    """Class for handle automatic finding faces on album's photos."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._path = self._prepare_path()

    def handle(self):
        for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False):
            image = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))
            faces = self._find_faces_on_image(image=image)
            self._print_photo_with_framed_faces(image=image, faces=faces, pk=photo.pk)
            self._save_photo_data(data=faces, pk=photo.pk)

        self._save_album_report()

    def _prepare_path(self):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/frames')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @staticmethod
    def _find_faces_on_image(image):
        face_locs = fr.face_locations(image)
        face_encs = fr.face_encodings(image)
        faces = [(location, encoding) for (location, encoding) in zip(face_locs, face_encs)]
        return faces

    def _print_photo_with_framed_faces(self, image, faces, pk):
        pil_image = Image.fromarray(image)
        draw = ImageDraw.Draw(pil_image)
        for i, (location, encoding) in enumerate(faces, 1):
            top, right, bottom, left = location
            draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=4)
            fontsize = (bottom - top) // 3
            font = ImageFont.truetype("arialbd.ttf", fontsize)
            draw.text((left, top), str(i), fill=(255, 0, 0), font=font)
        del draw
        pil_image.save(os.path.join(self._path, f"photo_{pk}.jpg"))

    def _save_photo_data(self, data, pk):
        i = 0
        for i, (location, encoding) in enumerate(data, 1):
            redis_instance.hset(f"photo_{pk}", f"face_{i}_location", pickle.dumps(location))
            redis_instance.hset(f"photo_{pk}", f"face_{i}_encoding", encoding.dumps())
        redis_instance.hset(f"photo_{pk}", "faces_amount", i)
        redis_instance.expire(f"photo_{pk}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hincrby(f"album_{self._album_pk}", "number_of_processed_photos")

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 1)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class RelateFacesHandler:
    """Class for automatic joining founded faces into patterns."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._path = self._prepare_path()
        self._queryset = Photos.objects.filter(album__pk=self._album_pk, is_private=False)
        self._patterns = []
        self._data = {}

    def handle(self):
        self._get_faces_data_from_redis()
        self._relate_faces_data()
        self._find_central_faces_of_patterns()
        self._save_patterns_data_to_redis()
        self._print_pattern_faces()
        self._save_album_report()

    def _get_faces_data_from_redis(self):
        for photo in self._queryset:
            faces_amount = int(redis_instance.hget(f"photo_{photo.pk}", f"faces_amount"))
            photo_faces = [FaceData(photo.pk, i,
                                    pickle.loads(redis_instance_raw.hget(f"photo_{photo.pk}", f"face_{i}_location")),
                                    pickle.loads(redis_instance_raw.hget(f"photo_{photo.pk}", f"face_{i}_encoding")))
                           for i in range(1, faces_amount+1)]
            self._data.update({photo.pk: photo_faces})

    def _relate_faces_data(self):
        for photo_pk, faces in self._data.items():
            if not self._patterns:
                self._patterns.extend([PatternData(face) for face in faces])
            else:
                for face in faces:
                    # comparing with already added faces
                    for pattern in self._patterns:
                        pattern_encodings = [saved_face.encoding for saved_face in pattern]
                        if self._is_same_face(face.encoding, pattern_encodings):
                            pattern.add_face(face)
                            break
                    else:
                        self._patterns.append(PatternData(face))

    @staticmethod
    def _is_same_face(face_enc, known_encs):
        result_list = fr.compare_faces(known_encs, face_enc, FACE_RECOGNITION_TOLERANCE)
        return sum(result_list) / len(result_list) > PATTERN_EQUALITY_TOLERANCE

    def _find_central_faces_of_patterns(self):
        for pattern in self._patterns:
            pattern.find_central_face()

    def _save_patterns_data_to_redis(self):
        for i, pattern in enumerate(self._patterns, 1):
            for j, face in enumerate(pattern, 1):
                redis_instance.hset(f"album_{self._album_pk}_pattern_{i}",
                                    f"face_{j}",
                                    f"photo_{face.photo_pk}_face_{face.index}")
                if face is pattern.central_face:
                    redis_instance.hset(f"album_{self._album_pk}_pattern_{i}",
                                        "central_face",
                                        f"face_{j}")

            redis_instance.hset(f"album_{self._album_pk}_pattern_{i}",
                                "faces_amount",
                                len(pattern))

    def _prepare_path(self):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/patterns')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def _print_pattern_faces(self):
        images = {}
        for photo in self._queryset:
            images[photo.pk] = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))

        for i, pattern in enumerate(self._patterns, 1):
            for j, face in enumerate(pattern, 1):
                top, right, bottom, left = face.location
                face_image = images.get(face.photo_pk)[top:bottom, left:right]
                pil_image = Image.fromarray(face_image)
                if j == 1:
                    os.makedirs(os.path.join(self._path, str(i)))
                save_path = os.path.join(self._path, str(i), f'{j}.jpg')
                pil_image.save(save_path)

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 3)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class ComparingExistingAndNewPeopleHandler:
    """Class for handling uniting people of processing album with previously created people of this user."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._album = None
        self._existing_people = []
        self._new_people = []
        self._pairs = []

    def handle(self):
        self._get_existing_people_data_from_db()
        self._get_new_people_data_from_redis()
        self._connect_people_in_pairs()
        self._save_united_people_data_to_redis()
        self._save_album_report()

    def _get_existing_people_data_from_db(self):
        queryset = Faces.objects.filter(
            pattern__person__owner__username=self._album.owner.username
        ).select_related(
            'pattern__person', 'photo', 'pattern__central_face'
        ).exclude(
            photo__album__pk=self._album_pk
        ).order_by('pattern__person', 'pattern')

        # Extracting data from db_instances
        person_db_instance = pattern_db_instance = None
        person = pattern = None
        for face_db_instance in queryset:
            face = FaceData(photo_pk=face_db_instance.photo.pk,
                            index=face_db_instance.index,
                            location=(face_db_instance.loc_top, face_db_instance.loc_right,
                                      face_db_instance.loc_bot, face_db_instance.loc_left),
                            encoding=pickle.loads(face_db_instance.encoding))

            if person_db_instance != face_db_instance.pattern.person:
                person_db_instance = face_db_instance.pattern.person
                person = PersonData(pk=person_db_instance.pk)
                self._existing_people.append(person)

            if pattern_db_instance != face_db_instance.pattern:
                pattern_db_instance = face_db_instance.pattern
                pattern = PatternData(face)
                person.add_pattern(pattern)
            else:
                pattern.add_face(face)

            if face_db_instance.pk == face_db_instance.pattern.central_face.pk:
                pattern.central_face = face

    def _get_new_people_data_from_redis(self):
        i = 1
        while redis_instance.exists(f"album_{self._album_pk}_person_{i}"):
            person = PersonData(redis_indx=i)

            j = 1
            while redis_instance.hexists(f"album_{self._album_pk}_person_{i}", f"pattern_{j}"):
                pattern_ind = int(redis_instance.hget(f"album_{self._album_pk}_person_{i}", f"pattern_{j}"))
                pattern_ccentral_face_ind = int(redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}",
                                                                    "central_face")[5:])

                for k in range(1, int(redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}",
                                                          "faces_amount")) + 1):
                    face_address = redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}", f"face_{k}")
                    photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
                    face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
                    face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
                    face = FaceData(photo_pk=int(photo_pk),
                                    index=int(face_ind),
                                    location=face_loc,
                                    encoding=face_enc)
                    if k == 1:
                        pattern = PatternData(face)
                    else:
                        pattern.add_face(face)

                    if k == pattern_ccentral_face_ind:
                        pattern.central_face = face

                person.add_pattern(pattern)
                j += 1

            self._new_people.append(person)
            i += 1

    def _connect_people_in_pairs(self):
        ppl_distances = []
        for old_per in self._existing_people:
            for new_per in self._new_people:
                dist = self._get_ppl_dist(old_per, new_per)
                if dist <= FACE_RECOGNITION_TOLERANCE:
                    ppl_distances.append((dist, old_per, new_per))

        ppl_distances.sort(key=lambda data: data[0])

        added_people = []
        for dist_data in ppl_distances:
            old_per, new_per = dist_data[1], dist_data[2]
            if old_per not in added_people and new_per not in added_people:
                self._pairs.append((old_per, new_per))
                added_people.append(old_per)
                added_people.append(new_per)

    @staticmethod
    def _get_ppl_dist(per1, per2):
        dist_data = []
        for pattern1 in per1:
            compare_encodings = list(map(lambda p: p.central_face.encoding, per2))
            distances = list(fr.face_distance(compare_encodings, pattern1.central_face.encoding))
            min_dist = min(distances)
            nearest_pat2_ind = distances.index(min_dist)
            dist_data.append((min_dist, pattern1, per2[nearest_pat2_ind]))

        _, pat1, pat2 = sorted(dist_data, key=lambda data: data[0])[0]

        dists = []
        for face1 in pat1:
            compare_encodings = list(map(lambda f: f.encoding, pat2))
            dists.extend(fr.face_distance(compare_encodings, face1.encoding))

        return min(dists)

    def _save_united_people_data_to_redis(self):
        for old_per, new_per in self._pairs:
            redis_instance.hset(f"album_{self._album_pk}_person_{new_per.redis_indx}",
                                "tech_pair", f"person_{old_per.pk}")

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 5)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class SavingAlbumRecognitionDataToDBHandler:
    """Class for saving recognition data of album to SQL Data Base from redis."""
    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._people = []
        self._patterns_queryset = None

    def handle(self):
        self._clear_db_album_data()
        self._get_data_from_redis()
        self._save_data_to_db()
        self._clear_redis_album_data()
        self._clear_temp_files()

    def _clear_db_album_data(self):
        album_faces = Faces.objects.filter(photo__album__pk=self._album_pk).select_related('pattern__person')
        related_patterns_pks = set(map(lambda f: f.pattern.pk, album_faces))
        related_people_pks = set(map(lambda f: f.pattern.person.pk, album_faces))

        album_faces.delete()
        Patterns.objects.filter(pk__in=related_patterns_pks,
                                faces__isnull=True).delete()
        People.objects.filter(pk__in=related_people_pks,
                              patterns__isnull=True).delete()

    def _get_data_from_redis(self):
        i = 1
        while redis_instance.exists(f"album_{self._album_pk}_person_{i}"):
            person = PersonData(redis_indx=i,
                                pair_pk=redis_instance.hget(f"album_{self._album_pk}_person_{i}", "real_pair"))

            j = 1
            while redis_instance.hexists(f"album_{self._album_pk}_person_{i}", f"pattern_{j}"):
                pattern_ind = redis_instance.hget(f"album_{self._album_pk}_person_{i}", f"pattern_{j}")
                pattern_ccentral_face_ind = int(redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}",
                                                                    "central_face")[5:])

                for k in range(1, int(redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}",
                                                          "faces_amount")) + 1):
                    face_address = redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}", f"face_{k}")
                    photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
                    face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
                    face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
                    face = FaceData(photo_pk=int(photo_pk),
                                    index=int(face_ind),
                                    location=face_loc,
                                    encoding=face_enc)
                    if k == 1:
                        pattern = PatternData(face)
                    else:
                        pattern.add_face(face)

                    if k == pattern_ccentral_face_ind:
                        pattern.central_face = face

                person.add_pattern(pattern)
                j += 1

            self._people.append(person)
            i += 1

    def _save_data_to_db(self):
        self._save_main_data()
        self._form_cluster_structure()

    def _save_main_data(self):
        album = Albums.objects.select_related('owner').prefetch_related('photos').get(pk=self._album_pk)

        # Forming model instances
        people_instances = []
        patterns_instances = []
        faces_instances = []
        for person in self._people:
            person_instance = People(owner=album.owner, name=f"user_{album.owner};album_{album}")
            for pattern in person:
                pattern_instance = Patterns(person=person_instance)
                for face in pattern:
                    top, right, bot, left = face.location
                    face_instance = Faces(photo=album.photos.get(pk=face.photo_pk),
                                          index=face.index,
                                          pattern=pattern_instance,
                                          loc_top=top, loc_right=right, loc_bot=bot, loc_left=left,
                                          encoding=face.encoding.dumps())
                    faces_instances.append(face_instance)
                    if pattern.central_face == face:
                        pattern_instance.central_face = face_instance
                patterns_instances.append(pattern_instance)
            people_instances.append(person_instance)

        # Saving instances to db
        People.objects.bulk_create(people_instances)
        self._patterns_queryset = Patterns.objects.bulk_create(patterns_instances)
        Faces.objects.bulk_create(faces_instances)

    def _form_cluster_structure(self):
        main_cluster = Clusters.objects.get(pk=1)
        main_pool = Clusters.objects.filter(parent__pk=1).select_related('center__central_face') &\
                    Patterns.objects.filter(cluster__pk=1).select_related('central_face')
        for pattern in self._patterns_queryset:
            pool = main_pool
            cluster = main_cluster
            while not len(pool) < CLUSTER_LIMIT:
                nearest = self._get_nearest_node(pool, pattern)
                if isinstance(nearest, Clusters):
                    cluster = nearest
                    pool = Clusters.objects.filter(parent__pk=cluster.pk).select_related('center__central_face') &\
                        Patterns.objects.filter(cluster__pk=cluster.pk).select_related('central_face')
                    continue
                elif isinstance(nearest, Patterns):
                    new_cluster = Clusters.objects.create(parent=nearest.cluster, center=nearest)
                    nearest.cluster = new_cluster
                    nearest.save()
                    pattern.cluster = new_cluster
                    pattern.save()
                    break
                else:
                    raise TypeError("Node of pool must be Clusters or Patterns type.")

            else:
                pattern.cluster = cluster
                pattern.save()

            cluster_len = cluster.patterns_set.all().count()
            if cluster_len > MINIMAL_CLUSTER_TO_RECALCULATE and cluster.patterns_set.filter(is_registered_in_cluster=False).count() / cluster_len\
                    >= UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT:
                self.recalculate_center(cluster)

    @classmethod
    def _get_nearest_node(cls, pool, pattern):
        compare_encodings = list(map(cls._get_node_encoding, pool))
        distances = list(fr.face_distance(compare_encodings, pickle.loads(pattern.central_face.encoding)))
        min_dist = min(distances)
        index = distances.index(min_dist)

        return pool[index]

    @staticmethod
    def _get_node_encoding(node):
        if isinstance(node, Clusters):
            return pickle.loads(node.center.central_face.encoding)
        elif isinstance(node, Patterns):
            return pickle.loads(node.central_face.encoding)
        else:
            raise TypeError("Node of pool must be Clusters or Patterns type.")

    @staticmethod
    def _get_node_central_faces(node):
        if isinstance(node, Clusters):
            return node.center.central_face
        elif isinstance(node, Patterns):
            return node.central_face
        else:
            raise TypeError("Node of pool must be Clusters or Patterns type.")

    @classmethod
    def recalculate_center(cls, cluster, first_loop=True):
        """Recursive function to recalculate center of cluster.
        Before the first iteration, the need for recalculation is checked."""
        if first_loop:
            cluster_len = cluster.patterns_set.all().count()
            cluster_changes = cluster.patterns_set.filter(is_registered_in_cluster=False).count() +\
                              cluster.not_recalc_patt_del
        if not first_loop or cluster_len > MINIMAL_CLUSTER_TO_RECALCULATE and \
                cluster_changes / cluster_len >= UNREGISTERED_PATTERNS_CLUSTER_RELEVANT_LIMIT:

            pool = cluster.patterns_set & cluster.clusters_set
            faces = list(map(cls._get_node_central_faces, pool))

            min_dist_sum = center_index = None
            for i, face in enumerate(faces):
                compare_face_list = faces.copy()
                compare_face_list.remove(face)
                compare_encs = list(map(lambda f: pickle.loads(f.encoding), compare_face_list))
                distances = fr.face_distance(compare_encs, pickle.loads(face.encoding))
                dist_sum = sum(distances)
                if min_dist_sum is None or dist_sum < min_dist_sum:
                    min_dist_sum = dist_sum
                    center_index = i

            # Reset counters
            for pattern in cluster.patterns_set.filter(is_registered_in_cluster=False):
                pattern.is_registered_in_cluster = True
                pattern.save(update_fields='is_registered_in_cluster')
            cluster.not_recalc_patt_del = 0
            cluster.save(update_fields='not_recalc_patt_del')

            center = pool[center_index]
            #If center changed
            if (not isinstance(center, Patterns) or cluster.center.pk != center.pk) and cluster.pk != 1:
                cluster.center = center if isinstance(center, Patterns) else center.center
                cluster.save()
                cls.recalculate_center(cluster.parent, first_loop=False)

    def _clear_redis_album_data(self):
        redis_instance.delete(f"album_{self._album_pk}",
                              f"album_{self._album_pk}_photos")
        redis_instance.delete(*[f"photo_{photo.pk}" for photo in Photos.objects.filter(album__pk=self._album_pk)])

        str_patterns = (f"album_{self._album_pk}_pattern_", f"album_{self._album_pk}_person_")
        for str_pattern in str_patterns:
            i = 1
            while redis_instance.exists(str_pattern + str(i)):
                redis_instance.delete(str_pattern + str(i))
                i += 1

    def _clear_temp_files(self):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}')
        os.system(f'rm -rf {path}')
