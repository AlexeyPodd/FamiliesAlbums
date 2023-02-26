import os
import re
import face_recognition as fr

import pickle
from PIL import Image
from django.db.models import Prefetch

from mainapp.models import Photos, Albums
from photoalbums.settings import BASE_DIR, REDIS_DATA_EXPIRATION_SECONDS, \
    FACE_RECOGNITION_TOLERANCE, PATTERN_EQUALITY_TOLERANCE, MEDIA_ROOT, SEARCH_PEOPLE_LIMIT

from .data_classes import FaceData, PatternData, PersonData
from .models import Faces, Patterns, People, Clusters
from .utils import set_album_photos_processed, redis_instance, redis_instance_raw
from .supporters import DataDeletionSupporter, ManageClustersSupporter, RedisSupporter


class BaseRecognitionHandler:
    """Base class for all recognition Handlers"""
    start_message_template = ""
    finish_message_template = ""

    def __init__(self, album_pk):
        self._album_pk = album_pk

    @property
    def start_message(self):
        return self.start_message_template.replace("album_pk", str(self._album_pk))

    @property
    def finish_message(self):
        return self.finish_message_template.replace("album_pk", str(self._album_pk))

    def handle(self):
        raise NotImplementedError


class FaceSearchingHandler(BaseRecognitionHandler):
    """Class for handle automatic finding faces on album's photos."""
    start_message_template = "Starting to process album_pk. Now searching for faces on album\'s photos."
    finish_message_template = "Search for faces on album_pk album\'s photos has been finished."

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._path = None

    def handle(self):
        self._get_path()
        self._prepare_to_recognition()
        self._face_search_and_save_to_redis()
        self._save_album_report()

    def _get_path(self):
        if self._path is None:
            self._path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/frames')

    def _prepare_to_recognition(self):
        DataDeletionSupporter.prepare_to_recognition(self._album_pk)
        set_album_photos_processed(album_pk=self._album_pk, status=False)

        photos_slugs = [photo.slug for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False)]
        redis_instance.rpush(f"album_{self._album_pk}_photos", *photos_slugs)
        redis_instance.expire(f"album_{self._album_pk}_photos", REDIS_DATA_EXPIRATION_SECONDS)

        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 1)
        redis_instance.hset(f"album_{self._album_pk}", "status", "processing")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _face_search_and_save_to_redis(self):
        for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False):
            image = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))
            faces = self._find_faces_on_image(image=image)
            self._save_photo_data_to_redis(data=faces, pk=photo.pk)
            if not faces:
                redis_instance.lrem(f"album_{self._album_pk}_photos", 1, photo.slug)

    @staticmethod
    def _find_faces_on_image(image):
        face_locs = fr.face_locations(image)
        face_encs = fr.face_encodings(image)
        faces = [(location, encoding) for (location, encoding) in zip(face_locs, face_encs)]
        return faces

    def _save_photo_data_to_redis(self, data, pk):
        i = 0
        for i, (location, encoding) in enumerate(data, 1):
            redis_instance.hset(f"photo_{pk}", f"face_{i}_location", pickle.dumps(location))
            redis_instance.hset(f"photo_{pk}", f"face_{i}_encoding", encoding.dumps())
        redis_instance.hset(f"photo_{pk}", "faces_amount", i)
        redis_instance.expire(f"photo_{pk}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hincrby(f"album_{self._album_pk}", "number_of_processed_photos")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 1)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class RelateFacesHandler(BaseRecognitionHandler):
    """Class for automatic joining founded faces into patterns."""
    start_message_template = "Starting to relate founded faces on photos of album album_pk."
    finish_message_template = "Relating faces of album_pk album has been finished."

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._path = None
        self._queryset = None
        self._patterns = []
        self._data = {}

    def handle(self):
        self._prepare_path()
        self._get_queryset()
        self._get_faces_data_from_redis()
        self._relate_faces_data()
        self._find_central_faces_of_patterns()
        self._save_patterns_data_to_redis()
        self._print_pattern_faces()
        self._save_album_report()

    def _get_queryset(self):
        if self._queryset is None:
            self._queryset = Photos.objects.filter(album__pk=self._album_pk, is_private=False)

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
            redis_instance.expire(f"album_{self._album_pk}_pattern_{i}", REDIS_DATA_EXPIRATION_SECONDS)

    def _prepare_path(self):
        if self._path is None:
            path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/patterns')
            if not os.path.exists(path):
                os.makedirs(path)
            self._path = path

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


class ComparingExistingAndNewPeopleHandler(BaseRecognitionHandler):
    """Class for handling uniting people of processing album with previously created people of this user."""
    start_message_template = "Starting to compare created people of album album_pk with previously created people."
    finish_message_template = "Comparing people of album_pk album with previously created people has been finished."

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._existing_people = []
        self._new_people = []
        self._pairs = []

    def handle(self):
        self._get_existing_people_data_from_db()
        self._get_new_people_data_from_redis_or_create_person()
        self._connect_people_in_pairs()
        self._save_united_people_data_to_redis()
        self._save_album_report()

    def _get_existing_people_data_from_db(self):
        queryset = Faces.objects.filter(
            pattern__person__owner__username=Albums.objects.select_related('owner').get(
                pk=self._album_pk
            ).owner.username
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

    def _get_new_people_data_from_redis_or_create_person(self):
        if redis_instance.exists(f"album_{self._album_pk}_person_1"):
            self._get_new_people_data_from_redis()
        elif redis_instance.exists(f"album_{self._album_pk}_pattern_1") and\
                not redis_instance.exists(f"album_{self._album_pk}_pattern_2"):
            self._create_person_from_pattern_and_set_it_to_redis()
        else:
            photo_pk = self._get_photo_pk_with_face()
            if photo_pk:
                self._create_person_from_face_and_set_it_to_redis(photo_pk=photo_pk)
                self._print_first_face()
            else:
                raise Exception(
                    "No people recognised and no patterns or it is not single pattern, or there is no faces at all."
                )

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

    def _create_person_from_pattern_and_set_it_to_redis(self):
        # Creating person
        person = PersonData(redis_indx=1)
        pattern_ccentral_face_ind = int(redis_instance.hget(f"album_{self._album_pk}_pattern_1",
                                                            "central_face")[5:])
        for i in range(1, int(redis_instance.hget(f"album_{self._album_pk}_pattern_1", "faces_amount")) + 1):
            face_address = redis_instance.hget(f"album_{self._album_pk}_pattern_1", f"face_{i}")
            photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
            face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
            face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
            face = FaceData(photo_pk=int(photo_pk),
                            index=int(face_ind),
                            location=face_loc,
                            encoding=face_enc)
            if i == 1:
                pattern = PatternData(face)
            else:
                pattern.add_face(face)

            if i == pattern_ccentral_face_ind:
                pattern.central_face = face

        person.add_pattern(pattern)
        self._new_people.append(person)

        # Setting it to redis
        redis_instance.hset(f"album_{self._album_pk}_person_1", "pattern_1", "1")
        redis_instance.hset(f"album_{self._album_pk}", "people_amount", "1")
        redis_instance.expire(f"album_{self._album_pk}_person_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _create_person_from_face_and_set_it_to_redis(self, photo_pk):
        person = PersonData(redis_indx=1)
        face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_location"))
        face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_encoding"))
        face = FaceData(photo_pk=int(photo_pk),
                        index=1,
                        location=face_loc,
                        encoding=face_enc)
        pattern = PatternData(face)
        person.add_pattern(pattern)
        self._new_people.append(person)

        # Setting it to redis
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "face_1", f"photo_{photo_pk}_face_1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "central_face", "face_1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "faces_amount", "1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "person", "1")
        redis_instance.hset(f"album_{self._album_pk}_person_1", "pattern_1", "1")
        redis_instance.hset(f"album_{self._album_pk}", "people_amount", "1")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_verified_patterns", "1")
        redis_instance.expire(f"album_{self._album_pk}_pattern_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}_person_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _print_first_face(self):
        face = next(iter(next(iter(self._new_people[0]))))

        # Cut face image
        image = fr.load_image_file(os.path.join(BASE_DIR, Photos.objects.get(pk=face.photo_pk).original.url[1:]))
        top, right, bottom, left = face.location
        face_image = image[top:bottom, left:right]
        pil_image = Image.fromarray(face_image)

        # Save face image to temp folder
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/patterns', '1')
        if not os.path.exists(path):
            os.makedirs(path)
        save_path = os.path.join(path, '1.jpg')
        pil_image.save(save_path)

    def _get_photo_pk_with_face(self):
        pks = map(lambda p: p.pk, Photos.objects.filter(album__pk=self._album_pk))
        photo_pk_with_face = None
        for pk in pks:
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                if photo_pk_with_face is None:
                    photo_pk_with_face = pk
                else:
                    raise Exception("Was founded multiple faces. Need relate them before saving.")

        return photo_pk_with_face

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
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 6)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class SavingAlbumRecognitionDataToDBHandler(BaseRecognitionHandler):
    """Class for saving recognition data of album to SQL Data Base from redis."""
    start_message_template = "Starting to save album album_pk recognition data to Data Base."
    finish_message_template = "Recognition data of album_pk album successfully saved to Data Base."

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._people = []
        self._new_patterns_instances = []

    def handle(self):
        self._get_data_from_redis()
        self._save_data_to_db()
        self._set_correct_status()
        self._set_finished_and_clear()

    def _get_data_from_redis(self):
        if redis_instance.exists(f"album_{self._album_pk}_person_1"):
            self._get_new_people_from_redis()
        elif redis_instance.exists(f"album_{self._album_pk}_pattern_1") and\
                not redis_instance.exists(f"album_{self._album_pk}_pattern_2"):
            self._create_person_from_pattern_and_set_it_to_redis()
        else:
            photo_pk = self._get_photo_pk_with_face()
            if photo_pk:
                self._create_person_from_face_and_set_it_to_redis(photo_pk=photo_pk)
            else:
                raise Exception(
                    "No people recognised and no patterns or it is not single pattern, or there is no faces at all."
                )

    def _get_photo_pk_with_face(self):
        pks = map(lambda p: p.pk, Photos.objects.filter(album__pk=self._album_pk))
        photo_pk_with_face = None
        for pk in pks:
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                if photo_pk_with_face is None:
                    photo_pk_with_face = pk
                else:
                    raise Exception("Was founded multiple faces. Need relate them before saving.")

        return photo_pk_with_face

    def _create_person_from_pattern_and_set_it_to_redis(self):
        person = PersonData(redis_indx=1)
        pattern_central_face_ind = int(redis_instance.hget(f"album_{self._album_pk}_pattern_1",
                                                           "central_face")[5:])
        for i in range(1, int(redis_instance.hget(f"album_{self._album_pk}_pattern_1",
                                                  "faces_amount")) + 1):
            face_address = redis_instance.hget(f"album_{self._album_pk}_pattern_1", f"face_{i}")
            photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
            face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
            face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
            face = FaceData(photo_pk=int(photo_pk),
                            index=int(face_ind),
                            location=face_loc,
                            encoding=face_enc)
            if i == 1:
                pattern = PatternData(face)
            else:
                pattern.add_face(face)

            if i == pattern_central_face_ind:
                pattern.central_face = face

        person.add_pattern(pattern)
        self._people.append(person)

        # Setting it to redis
        redis_instance.hset(f"album_{self._album_pk}_person_1", "patterns_1", "1")
        redis_instance.hset(f"album_{self._album_pk}", "people_amount", "1")
        redis_instance.expire(f"album_{self._album_pk}_person_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _create_person_from_face_and_set_it_to_redis(self, photo_pk):
        person = PersonData(redis_indx=1)
        face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_location"))
        face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_encoding"))
        face = FaceData(photo_pk=int(photo_pk),
                        index=1,
                        location=face_loc,
                        encoding=face_enc)
        pattern = PatternData(face)
        person.add_pattern(pattern)
        self._people.append(person)

        # Setting it to redis
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "face_1", f"photo_{photo_pk}_face_1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "faces_amount", "1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "person", "1")
        redis_instance.hset(f"album_{self._album_pk}_pattern_1", "central_face", "1")
        redis_instance.hset(f"album_{self._album_pk}_person_1", "pattern_1", "1")
        redis_instance.hset(f"album_{self._album_pk}", "people_amount", "1")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_verified_patterns", "1")
        redis_instance.expire(f"album_{self._album_pk}_pattern_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}_person_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _get_new_people_from_redis(self):
        i = 1
        while redis_instance.exists(f"album_{self._album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{self._album_pk}_person_{i}", "real_pair"):
                pair_pk = int(redis_instance.hget(f"album_{self._album_pk}_person_{i}", "real_pair")[7:])
            else:
                pair_pk = None
            person = PersonData(redis_indx=i, pair_pk=pair_pk)

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
        ManageClustersSupporter.form_cluster_structure(self._new_patterns_instances)
        set_album_photos_processed(album_pk=self._album_pk, status=True)

    def _save_main_data(self):
        album = Albums.objects.select_related('owner').prefetch_related('photos_set').get(pk=self._album_pk)

        count_new_people = 0
        for person in self._people:
            if person.pair_pk is None:
                count_new_people += 1
                self._create_person_instance(person, album, person_number_in_album=count_new_people)
            else:
                self._update_person_instance(person, album)

    def _create_person_instance(self, person_data, album, person_number_in_album):
        person_instance = People(owner=album.owner,
                                 name=f"{album.title[:20]}__{person_number_in_album}__{album.owner.username[:10]}")
        person_instance.save()

        patterns_instances = []
        # Saving patterns
        for pattern_data in person_data:
            pattern_instance = Patterns(person=person_instance)
            pattern_instance.save()
            patterns_instances.append(pattern_instance)
            # Saving faces
            for face_data in pattern_data:
                top, right, bot, left = face_data.location
                face_instance = Faces(photo=album.photos_set.get(pk=face_data.photo_pk),
                                      index=face_data.index,
                                      pattern=pattern_instance,
                                      loc_top=top, loc_right=right, loc_bot=bot, loc_left=left,
                                      encoding=face_data.encoding.dumps())
                face_instance.save()

                # Saving central face of pattern
                if pattern_data.central_face == face_data:
                    pattern_instance.central_face = face_instance
                    pattern_instance.save(update_fields=['central_face'])

        self._new_patterns_instances.extend(patterns_instances)

    def _update_person_instance(self, person_data, album):
        created_patterns_instances = []
        old_person_data, person_instance = self._get_old_person(person_pk=person_data.pair_pk, album=album)

        # Creating new pattern, ot uniting with old one, if it already exists
        for new_pattern_data in person_data:
            united_pattern_data = None
            for old_pattern_data, old_pattern_instance in zip(old_person_data, person_instance.patterns_set.all()):
                if new_pattern_data == old_pattern_data:
                    pattern_instance = old_pattern_instance
                    united_pattern_data = self._create_united_pattern_data(new_pattern_data, old_pattern_data)
                    break
            else:
                pattern_instance = Patterns(person=person_instance)
                pattern_instance.save()
                created_patterns_instances.append(pattern_instance)

            # The central face, depending on whether a new pattern is created or an old one is expanded,
            # is central face a new one or already existing
            if united_pattern_data is None:
                calculated_central_face_data = new_pattern_data.central_face
            else:
                calculated_central_face_data = united_pattern_data.central_face

            if calculated_central_face_data.pk is None:
                central_face_is_new = True
            else:
                central_face_is_new = False
                pattern_instance.central_face = Faces.objects.get(pk=calculated_central_face_data.pk)
                pattern_instance.save(update_fields=['central_face'])

            # Saving faces
            for face_data in new_pattern_data:
                top, right, bot, left = face_data.location
                face_instance = Faces(photo=album.photos_set.get(pk=face_data.photo_pk),
                                      index=face_data.index,
                                      pattern=pattern_instance,
                                      loc_top=top, loc_right=right, loc_bot=bot, loc_left=left,
                                      encoding=face_data.encoding.dumps())
                face_instance.save()

                # If central face is a new one - linking it
                if central_face_is_new and calculated_central_face_data == face_data:
                    pattern_instance.central_face = face_instance
                    pattern_instance.save(update_fields=['central_face'])

        self._new_patterns_instances.extend(created_patterns_instances)

    @staticmethod
    def _create_united_pattern_data(new_pattern, old_pattern):
        for i, face in enumerate(old_pattern):
            if i == 0:
                pattern = PatternData(face)
            else:
                pattern.add_face(face)
        for face in new_pattern:
            pattern.add_face(face)
        pattern.find_central_face()
        return pattern

    @staticmethod
    def _get_old_person(person_pk, album):
        person_instance = People.objects.prefetch_related(
            Prefetch('patterns_set__faces_set',
                     queryset=Faces.objects.filter(photo__album__owner__pk=album.owner.pk).select_related('photo'))
        ).get(pk=person_pk)

        person = PersonData(pk=person_pk)
        for pattern_instance in person_instance.patterns_set.all():
            for i, face_instance in enumerate(pattern_instance.faces_set.all()):
                face = FaceData(photo_pk=face_instance.photo.pk,
                                index=face_instance.index,
                                location=(face_instance.loc_top, face_instance.loc_right,
                                          face_instance.loc_bot, face_instance.loc_left),
                                encoding=pickle.loads(face_instance.encoding),
                                pk=face_instance.pk)
                if i == 0:
                    pattern = PatternData(face)
                else:
                    pattern.add_face(face)
            person.add_pattern(pattern)

        return person, person_instance

    def _set_correct_status(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 9)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _set_finished_and_clear(self):
        redis_instance.set(f"album_{self._album_pk}_finished", 1)
        redis_instance.expire(f"album_{self._album_pk}_finished", REDIS_DATA_EXPIRATION_SECONDS)
        DataDeletionSupporter.clean_after_recognition(album_pk=self._album_pk)


class ClearTempDataHandler(BaseRecognitionHandler):
    """Class for clearing temporary system files and redis after processing album photos."""
    start_message_template = "Starting to delete temp files and redis data of album album_pk."
    finish_message_template = "Deletion temp files and redis data of album_pk album successfully done."

    def handle(self):
        DataDeletionSupporter.clean_after_recognition(album_pk=self._album_pk)


class SimilarPeopleSearchingHandler:
    """Class for searching people in other users photos, who look like the person in the user's photos.
    Search is based on patterns in the fractal structure of clusters."""
    start_message_template = "Starting to search person person_pk."
    finish_message_template = "Search of person person_pk is finished."

    def __init__(self, person_pk):
        self._person_pk = person_pk

    @property
    def start_message(self):
        return self.start_message_template.replace("person_pk", str(self._person_pk))

    @property
    def finish_message(self):
        return self.finish_message_template.replace("person_pk", str(self._person_pk))

    def handle(self):
        self._owner_pk = People.objects.select_related('owner').get(pk=self._person_pk).owner.pk
        similar_people_pks = self._find_similar_people()
        RedisSupporter.set_founded_similar_people(person_pk=self._person_pk, pks=similar_people_pks)

    def _find_similar_people(self):
        person_patterns = Patterns.objects.filter(person__pk=self._person_pk).select_related('central_face')
        nearest_people = {}
        for pattern in person_patterns:
            nearest_patterns = self._find_nearest_patterns(
                pattern_central_encoding=pickle.loads(pattern.central_face.encoding),
            )
            for patt, distance in nearest_patterns:
                if nearest_people.setdefault(patt.person, distance) > distance:
                    nearest_people[patt.person] = distance

            RedisSupporter.encrease_patterns_search_amount(self._person_pk)

        list_of_nearest_people = sorted(filter(lambda p: p.pk != self._person_pk and p.owner.pk != self._owner_pk,
                                               nearest_people.keys()), key=lambda k: nearest_people[k])
        return [person.pk for person in list_of_nearest_people][:SEARCH_PEOPLE_LIMIT]

    def _find_nearest_patterns(self, pattern_central_encoding, pool=None):
        """Recursive function for finding roughly nearest patterns in fractal structure."""
        if pool is None:
            pool = [(Clusters.objects.prefetch_related('patterns_set', 'clusters_set').get(pk=1), 0)]

        if any(map(lambda t: isinstance(t[0], Clusters), pool)):
            collected_nodes = []
            for node, distance in pool:
                if len(collected_nodes) >= SEARCH_PEOPLE_LIMIT * 3 and\
                        all(map(lambda t: t[1] < distance, collected_nodes)):
                    break
                elif isinstance(node, Clusters):
                    subclusters = node.clusters_set.all()
                    if subclusters:
                        subclusters_encodings = list(map(lambda sub: pickle.loads(sub.center.central_face.encoding),
                                                         subclusters))
                        subclusters_distances = fr.face_distance(subclusters_encodings, pattern_central_encoding)
                        collected_nodes.extend(list(zip(subclusters, subclusters_distances)))

                    subpatterns = node.patterns_set.all()
                    if subpatterns:
                        subpatterns_encodings = list(map(lambda sub: pickle.loads(sub.central_face.encoding),
                                                         subpatterns))
                        subpatterns_distances = fr.face_distance(subpatterns_encodings, pattern_central_encoding)
                        collected_nodes.extend(list(zip(subpatterns, subpatterns_distances)))
                else:
                    collected_nodes.extend([(node, distance)])

            collected_nodes.sort(key=lambda t: t[1])
            nearest_nodes = collected_nodes[:SEARCH_PEOPLE_LIMIT * 3]
            return self._find_nearest_patterns(pattern_central_encoding=pattern_central_encoding, pool=nearest_nodes)

        else:
            return pool
