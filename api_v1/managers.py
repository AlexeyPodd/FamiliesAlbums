import os

from mainapp.models import Photos
from photoalbums.settings import MEDIA_ROOT
from recognition.models import Faces, People
from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus
from recognition.redis_interface.views_api import RedisAPIStage2View, RedisAPIStage4View, RedisAPIStage5View, \
    RedisAPIStage7View, RedisAPIStage8View
from recognition.supporters import DataDeletionSupporter
from recognition.tasks import recognition_task
from recognition.utils import set_album_photos_processed


class AlbumProcessingManager:
    def __init__(self, data_collector, user):
        self.data_collector = data_collector
        self.user = user

    def run(self):
        raise NotImplementedError

    def _start_celery_task(self, next_stage):
        self.redisAPI.set_stage(album_pk=self.data_collector.album_pk, stage=next_stage)
        self.redisAPI.set_status(album_pk=self.data_collector.album_pk, status="processing")
        recognition_task.delay(self.data_collector.album_pk, next_stage)

    def _choose_celery_task_and_start_it(self):
        another_album_processed = Faces.objects.filter(
            photo__album__owner=self.user,
        ).exclude(photo__album_id=self.data_collector.album_pk).exists()
        next_stage = 6 if another_album_processed else 9
        self._start_celery_task(next_stage)

    def _set_correct_status(self):
        self.redisAPI.set_stage(album_pk=self.data_collector.album_pk, stage=self.recognition_stage)
        self.redisAPI.set_status(album_pk=self.data_collector.album_pk, status="completed")


class StartProcessingManager(AlbumProcessingManager):
    def run(self):
        RedisAPIStage.set_stage(album_pk=self.data_collector.album_pk, stage=0)
        RedisAPIStatus.set_status(album_pk=self.data_collector.album_pk, status="processing")
        recognition_task.delay(self.data_collector.album_pk, 1)


class VerifyFramesManager(AlbumProcessingManager):
    recognition_stage = 2
    redisAPI = RedisAPIStage2View

    def run(self):
        photos = Photos.objects.filter(album_id=self.data_collector.album_pk)
        self._update_photos_data(photos)
        self._set_correct_status()

        self._count_photos_with_verified_faces(photos)
        if self._photos_with_faces_amount == 0:
            self._finalize_recognition()
        else:
            self._start_celery_task(next_stage=self._get_next_stage())

    def _update_photos_data(self, photos):
        for photo in photos:
            self._delete_wrong_data(photo)
            self.redisAPI.renumber_faces_of_photo(photo.pk)
            self.redisAPI.register_photo_processed(self.data_collector.album_pk)

    def _finalize_recognition(self):
        self.redisAPI.set_no_faces(self.data_collector.album_pk)
        DataDeletionSupporter.clean_after_recognition(album_pk=self.data_collector.album_pk)
        set_album_photos_processed(album_pk=self.data_collector.album_pk, status=True)

    def _delete_wrong_data(self, photo):
        for face_number in self.data_collector.data[photo.slug]:
            face_name = f"face_{face_number}"
            self.redisAPI.del_face(photo.pk, face_name)

    def _count_photos_with_verified_faces(self, photos):
        count = 0
        for pk in map(lambda p: p.pk, photos):
            if self.redisAPI.is_face_in_photo(photo_pk=pk, face_index=1):
                count += 1
        self._photos_with_faces_amount = count

    def _get_next_stage(self):
        another_processed_album_has_faces = Faces.objects.filter(
            photo__album__owner=self.user,
        ).exclude(photo__album_id=self.data_collector.album_pk).exists()

        if self._photos_with_faces_amount == 1 and another_processed_album_has_faces:
            return 6
        elif self._photos_with_faces_amount == 1:
            return 9
        else:
            return 3

    def _set_correct_status(self):
        super()._set_correct_status()
        self.redisAPI.reset_processed_photos_amount(self.data_collector.album_pk)


class VerifyPatternsManager(AlbumProcessingManager):
    recognition_stage = 4
    redisAPI = RedisAPIStage4View

    def run(self):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self.data_collector.album_pk}/patterns')
        patterns_amount = self._split_patterns(path)
        self._renumber_patterns_faces_data_and_files(patterns_amount=patterns_amount, patterns_dir=path)
        self._recalculate_patterns_centers(patterns_amount)
        self.redisAPI.register_verified_patterns(self.data_collector.album_pk, patterns_amount)

        self._set_correct_status()

        if patterns_amount == 1:
            self._choose_celery_task_and_start_it()

    def _split_patterns(self, patterns_dir):
        patterns_amount = len(self.data_collector.data)
        for i, (pattern_name, separated_faces) in enumerate(self.data_collector.data.items(), 1):
            faces_amount = self.redisAPI.get_pattern_faces_amount(self.data_collector.album_pk, i)
            for faces_list in separated_faces[1:]:
                patterns_amount += 1
                self.redisAPI.set_pattern_faces_amount(album_pk=self.data_collector.album_pk,
                                                       pattern_index=patterns_amount,
                                                       faces_amount=faces_amount)
                for j, face_name in enumerate(faces_list):
                    # Moving face's data in redis
                    self.redisAPI.move_face_data(album_pk=self.data_collector.album_pk, face_name=face_name,
                                                 from_pattern=i, to_pattern=patterns_amount)

                    # Moving face image in temp directory
                    if j == 0:
                        os.makedirs(os.path.join(patterns_dir, str(patterns_amount)))
                    old_path = os.path.join(patterns_dir, str(i), f"{face_name[5:]}.jpg")
                    new_path = os.path.join(patterns_dir, str(patterns_amount), f"{face_name[5:]}.jpg")
                    os.replace(old_path, new_path)

        return patterns_amount

    def _renumber_patterns_faces_data_and_files(self, patterns_amount, patterns_dir):
        for i in range(1, patterns_amount + 1):
            faces_amount = self.redisAPI.get_pattern_faces_amount(self.data_collector.album_pk, i)

            # Renumbering files
            count = 0
            for j in range(1, faces_amount + 1):
                if self.redisAPI.is_face_in_pattern(self.data_collector.album_pk, face_index=j, pattern_index=i):
                    count += 1
                    if count != j:
                        old_path = os.path.join(patterns_dir, str(i), f"{j}.jpg")
                        new_path = os.path.join(patterns_dir, str(i), f"{count}.jpg")
                        os.replace(old_path, new_path)

            # Renumbering redis data
            self.redisAPI.renumber_faces_in_patterns(album_pk=self.data_collector.album_pk, pattern_index=i,
                                                     faces_amount=faces_amount)

    def _recalculate_patterns_centers(self, patterns_amount):
        for i in range(1, patterns_amount + 1):
            if self.redisAPI.get_pattern_faces_amount(self.data_collector.album_pk, i) > 1:
                self.redisAPI.recalculate_pattern_center(self.data_collector.album_pk, i)
            else:
                self.redisAPI.set_single_face_central_in_pattern(self.data_collector.album_pk, i)


class GroupPatternsManager(AlbumProcessingManager):
    recognition_stage = 5
    redisAPI = RedisAPIStage5View

    def run(self):
        self._group_patterns_into_people()
        self._choose_celery_task_and_start_it()

    def _group_patterns_into_people(self):
        for i, person_patterns in enumerate(self.data_collector.data, 1):
            self.redisAPI.set_created_person(album_pk=self.data_collector.album_pk, pattern_name=person_patterns[0])
            for j, pattern in enumerate(person_patterns[1:], 2):
                self.redisAPI.set_pattern_to_person(album_pk=self.data_collector.album_pk,
                                                    pattern_name=pattern,
                                                    pattern_number_in_person=j,
                                                    person_number=i)


class VerifyTechPeopleMatchesManager(AlbumProcessingManager):
    recognition_stage = 7
    redisAPI = RedisAPIStage7View

    def run(self):
        self._register_matches_to_redis()
        self._set_correct_status()
        if not self._check_pairing_possibility():
            self._start_celery_task(next_stage=9)

    def _register_matches_to_redis(self):
        for new_per_name, old_per_pk in self.data_collector.data.values():
            new_per_ind = new_per_name[7:]
            self.redisAPI.set_new_pair(self.data_collector.album_pk, new_per_ind, old_per_pk)

    def _check_pairing_possibility(self):
        return self._check_new_single_people() and self._check_old_single_people()

    def _check_new_single_people(self):
        return self.redisAPI.check_existing_new_single_people(album_pk=self.data_collector.album_pk)

    def _check_old_single_people(self):
        queryset = People.objects.filter(owner=self.user)

        # Collecting already paired people with created people of this album
        paired = self.redisAPI.get_old_paired_people(self.data_collector.album_pk)

        # Iterating through people, filtering already paired
        for person in queryset:
            if person.pk not in paired:
                return True
        return False


class ManualMatchingPeopleManager(AlbumProcessingManager):
    recognition_stage = 8
    redisAPI = RedisAPIStage8View

    def run(self):
        self._register_matches_to_redis()
        self._set_correct_status()
        self._start_celery_task(next_stage=9)

    def _register_matches_to_redis(self):
        for new_per_name, old_per_pk in self.data_collector.data.values():
            new_per_ind = new_per_name[7:]
            self.redisAPI.set_new_pair(self.data_collector.album_pk, new_per_ind, old_per_pk)
