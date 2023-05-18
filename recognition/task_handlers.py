import os
import face_recognition as fr

import pickle
from PIL import Image
from django.db.models import Prefetch

from mainapp.models import Photos, Albums
from photoalbums.settings import BASE_DIR, FACE_RECOGNITION_TOLERANCE, PATTERN_EQUALITY_TOLERANCE, \
    SEARCH_PEOPLE_LIMIT, TEMP_ROOT

from .data_classes import FaceData, PatternData, PersonData
from .models import Faces, Patterns, People, Clusters
from .redis_interface.task_handlers_api import RedisAPIStage1Handler, RedisAPIStage3Handler, RedisAPIStage6Handler, \
    RedisAPIStage9Handler, RedisAPISearchHandler
from .utils import set_album_photos_processed
from .supporters import DataDeletionSupporter, ManageClustersSupporter


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
        self._save_album_report()

    def _save_album_report(self):
        self.redisAPI.set_stage(self._album_pk, stage=self.stage)
        self.redisAPI.set_status(self._album_pk, status="completed")
        self.redisAPI.reset_processed_photos_amount(self._album_pk)


class BaseRecognitionLateStageHandler(BaseRecognitionHandler):
    def _get_new_people_data_from_redis_or_create_people(self):
        if self.redisAPI.check_any_person_found(self._album_pk):
            self._new_people = self.redisAPI.get_people_data(self._album_pk)
        elif self.redisAPI.check_single_pattern_formed(self._album_pk):
            self._create_person_from_pattern_and_set_it_to_redis()
        else:
            photo_pk = self._get_photo_pk_with_faces()
            if photo_pk:
                self._create_people_from_faces_and_set_them_to_redis(photo_pk=photo_pk)
                self._print_faces_of_single_photo_with_faces()
            else:
                raise Exception("No people recognised and multiple patterns, or there is no faces at all.")

    def _get_photo_pk_with_faces(self):
        pks = map(lambda p: p.pk, Photos.objects.filter(album__pk=self._album_pk))
        return self.redisAPI.get_single_photo_with_faces(photos_pks=pks)

    def _create_person_from_pattern_and_set_it_to_redis(self):
        # Creating person
        person_data = self.redisAPI.create_person_from_single_pattern(self._album_pk)
        self._new_people.append(person_data)

        # Setting it to redis
        self.redisAPI.set_one_person_with_one_pattern(self._album_pk)

    def _create_people_from_faces_and_set_them_to_redis(self, photo_pk):
        # Creating people
        people_data = self.redisAPI.create_people_from_faces_on_single_photo(photo_pk)
        self._new_people.extend(people_data)

        # Setting them to redis
        self.redisAPI.set_people_with_one_pattern_with_one_face_from_single_photo(self._album_pk, photo_pk,
                                                                                  faces_amount=len(people_data))

    def _print_faces_of_single_photo_with_faces(self):
        for i, face in enumerate(map(lambda person: person[0].central_face, self._new_people), 1):

            # Cut face image
            image = fr.load_image_file(os.path.join(BASE_DIR, Photos.objects.get(pk=face.photo_pk).original.url[1:]))
            top, right, bottom, left = face.location
            face_image = image[top:bottom, left:right]
            pil_image = Image.fromarray(face_image)

            # Save face image to temp folder
            path = os.path.join(TEMP_ROOT, f'album_{self._album_pk}/patterns', str(i))
            if not os.path.exists(path):
                os.makedirs(path)
            save_path = os.path.join(path, '1.jpg')
            pil_image.save(save_path)


class FaceSearchingHandler(BaseRecognitionHandler):
    """Class for handle automatic finding faces on album's photos."""
    start_message_template = "Starting to process album_pk. Now searching for faces on album\'s photos."
    finish_message_template = "Search for faces on album_pk album\'s photos has been finished."
    stage = 1
    redisAPI = RedisAPIStage1Handler

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._path = None

    def handle(self):
        self._get_path()
        self._prepare_to_recognition()
        self._face_search_and_save_to_redis()
        super().handle()

        # if no faces found
        if self.redisAPI.get_photo_slugs_amount(self._album_pk) == 0:
            self.redisAPI.set_no_faces(self._album_pk)
            DataDeletionSupporter.clean_after_recognition(album_pk=self._album_pk)
            set_album_photos_processed(album_pk=self._album_pk, status=True)

    def _get_path(self):
        if self._path is None:
            self._path = os.path.join(TEMP_ROOT, f'album_{self._album_pk}/frames')

    def _prepare_to_recognition(self):
        DataDeletionSupporter.prepare_to_recognition(self._album_pk)
        set_album_photos_processed(album_pk=self._album_pk, status=False)

        photos_slugs = [photo.slug for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False)]
        self.redisAPI.set_photos_slugs(self._album_pk, photos_slugs)

        self.redisAPI.set_stage(self._album_pk, stage=1)
        self.redisAPI.set_status(self._album_pk, status="processing")
        self.redisAPI.reset_processed_photos_amount(self._album_pk)

    def _face_search_and_save_to_redis(self):
        for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False):
            image = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))
            faces = self._find_faces_on_image(image=image)
            self.redisAPI.set_photo_faces_data(album_pk=self._album_pk, photo_pk=photo.pk, data=faces)
            if not faces:
                self.redisAPI.delete_photo_slug(self._album_pk, photo.slug)

    @staticmethod
    def _find_faces_on_image(image):
        face_locs = fr.face_locations(image)
        face_encs = fr.face_encodings(image)
        faces = [(location, encoding) for (location, encoding) in zip(face_locs, face_encs)]
        return faces


class RelateFacesHandler(BaseRecognitionHandler):
    """Class for automatic joining founded faces into patterns."""
    start_message_template = "Starting to relate founded faces on photos of album album_pk."
    finish_message_template = "Relating faces of album_pk album has been finished."
    stage = 3
    redisAPI = RedisAPIStage3Handler

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
        super().handle()

        if self._all_patterns_have_single_faces():
            self._set_patterns_to_redis_and_set_next_stage_completed()

    def _get_queryset(self):
        if self._queryset is None:
            self._queryset = Photos.objects.filter(album__pk=self._album_pk, is_private=False)

    def _get_faces_data_from_redis(self):
        for photo in self._queryset:
            photo_faces = self.redisAPI.get_faces_data_of_photo(photo.pk)
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
        self.redisAPI.set_patterns_data(self._album_pk, self._patterns)

    def _prepare_path(self):
        if self._path is None:
            path = os.path.join(TEMP_ROOT, f'album_{self._album_pk}/patterns')
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

    def _all_patterns_have_single_faces(self):
        return all(map(lambda p: len(p) == 1, self._patterns))

    def _set_patterns_to_redis_and_set_next_stage_completed(self):
        self.redisAPI.register_verified_patterns(self._album_pk, len(self._patterns))
        self.redisAPI.set_single_face_central(album_pk=self._album_pk,
                                              total_patterns_amount=len(self._patterns),
                                              skip=0)
        self.redisAPI.set_stage(album_pk=self._album_pk, stage=4)
        self.redisAPI.set_status(album_pk=self._album_pk, status="completed")


class ComparingExistingAndNewPeopleHandler(BaseRecognitionLateStageHandler):
    """Class for handling uniting people of processing album with previously created people of this user."""
    start_message_template = "Starting to compare created people of album album_pk with previously created people."
    finish_message_template = "Comparing people of album_pk album with previously created people has been finished."
    stage = 6
    redisAPI = RedisAPIStage6Handler

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._existing_people = []
        self._new_people = []
        self._pairs = []

    def handle(self):
        self._get_existing_people_data_from_db()
        self._get_new_people_data_from_redis_or_create_people()
        self._connect_people_in_pairs()
        self._save_united_people_data_to_redis()
        super().handle()

        if not self.redisAPI.check_any_tech_matches(self._album_pk):
            self._set_next_stage_completed()

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
        self.redisAPI.set_matching_people(self._album_pk, self._pairs)

    def _set_next_stage_completed(self):
        self.redisAPI.set_stage(album_pk=self._album_pk, stage=7)
        self.redisAPI.set_status(album_pk=self._album_pk, status="completed")


class SavingAlbumRecognitionDataToDBHandler(BaseRecognitionLateStageHandler):
    """Class for saving recognition data of album to SQL Data Base from redis."""
    start_message_template = "Starting to save album album_pk recognition data to Data Base."
    finish_message_template = "Recognition data of album_pk album successfully saved to Data Base."
    stage = 9
    redisAPI = RedisAPIStage9Handler

    def __init__(self, album_pk):
        super().__init__(album_pk)
        self._new_people = []
        self._new_patterns_instances = []

    def handle(self):
        self._get_new_people_data_from_redis_or_create_people()
        self._save_data_to_db()
        self._save_album_report()
        self._set_finished_and_clear()

    def _save_data_to_db(self):
        self._save_main_data()
        ManageClustersSupporter.form_cluster_structure(self._new_patterns_instances)
        set_album_photos_processed(album_pk=self._album_pk, status=True)

    def _save_main_data(self):
        album = Albums.objects.select_related('owner').prefetch_related('photos_set').get(pk=self._album_pk)

        count_new_people = 0
        for person in self._new_people:
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

    def _set_finished_and_clear(self):
        self.redisAPI.set_finished(self._album_pk)
        DataDeletionSupporter.clean_after_recognition(self._album_pk)


class ClearTempDataHandler(BaseRecognitionHandler):
    """Class for clearing temporary system files and redis after processing album photos."""
    start_message_template = "Starting to delete temp files and redis data of album album_pk."
    finish_message_template = "Deletion temp files and redis data of album_pk album successfully done."
    stage = -1

    def handle(self):
        DataDeletionSupporter.clean_after_recognition(album_pk=self._album_pk)


class SimilarPeopleSearchingHandler:
    """Class for searching people in other users photos, who look like the person in the user's photos.
    Search is based on patterns in the fractal structure of clusters."""
    start_message_template = "Starting to search person person_pk."
    finish_message_template = "Search of person person_pk is finished."
    stage = 0
    redisAPI = RedisAPISearchHandler

    def __init__(self, person_pk):
        self._person_pk = person_pk

    @property
    def start_message(self):
        return self.start_message_template.replace("person_pk", str(self._person_pk))

    @property
    def finish_message(self):
        return self.finish_message_template.replace("person_pk", str(self._person_pk))

    def handle(self):
        self.redisAPI.set_person_searching(self._person_pk)
        self._owner_pk = People.objects.select_related('owner').get(pk=self._person_pk).owner.pk
        similar_people_pks = self._find_similar_people()
        self.redisAPI.set_founded_similar_people(person_pk=self._person_pk, pks=similar_people_pks)
        self.redisAPI.set_person_not_searching(self._person_pk)

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

            self.redisAPI.encrease_patterns_search_amount(self._person_pk)

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
