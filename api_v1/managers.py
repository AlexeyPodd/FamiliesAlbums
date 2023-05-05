import os

from mainapp.models import Photos
from photoalbums.settings import MEDIA_ROOT
from recognition.models import Faces
from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus
from recognition.redis_interface.views_api import RedisAPIStage2View, RedisAPIStage4View
from recognition.supporters import DataDeletionSupporter
from recognition.tasks import recognition_task
from recognition.utils import set_album_photos_processed


class AlbumProcessingManager:
    def __init__(self, data_collector, user):
        self.data_collector = data_collector
        self.user = user

    def run(self):
        raise NotImplementedError


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

    def _start_celery_task(self, next_stage):
        self.redisAPI.set_stage(album_pk=self.data_collector.album_pk, stage=next_stage)
        self.redisAPI.set_status(album_pk=self.data_collector.album_pk, status="processing")
        recognition_task.delay(self.data_collector.album_pk, next_stage)

    def _set_correct_status(self):
        self.redisAPI.set_stage(album_pk=self.data_collector.album_pk, stage=self.recognition_stage)
        self.redisAPI.set_status(album_pk=self.data_collector.album_pk, status="completed")
        self.redisAPI.reset_processed_photos_amount(self.data_collector.album_pk)


# class VerifyPatternsManager(AlbumProcessingManager):
#     recognition_stage = 4
#     redisAPI = RedisAPIStage4View
#
#     def run(self):
#         path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self.data_collector.album_pk}/patterns')
#         self._replace_odd_faces_to_new_pattern()
#         self._renumber_patterns_faces_data_and_files()
#         self._recalculate_patterns_centers()
#         self.redisAPI.register_verified_patterns()
#         self._set_correct_status()
#
#         self._another_album_processed = Faces.objects.filter(
#             photo__album__owner=self.user,
#         ).exclude(photo__album_id=self.data_collector.album_pk).exists()
#         if patterns_amount == 1:
#             next_stage = 6 if self._another_album_processed else 9
#             self._start_celery_task(next_stage=next_stage)
