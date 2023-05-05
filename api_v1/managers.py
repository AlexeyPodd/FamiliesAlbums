from mainapp.models import Photos
from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus
from recognition.redis_interface.views_api import RedisAPIStage2View
from recognition.supporters import DataDeletionSupporter
from recognition.tasks import recognition_task
from recognition.utils import set_album_photos_processed


class AlbumProcessingManager:
    def __init__(self, data_collector):
        self.data_collector = data_collector

    def run(self):
        raise NotImplementedError


class StartProcessingManager(AlbumProcessingManager):
    def run(self):
        RedisAPIStage.set_stage(album_pk=self.data_collector.album_pk, stage=0)
        RedisAPIStatus.set_status(album_pk=self.data_collector.album_pk, status="processing")
        recognition_task.delay(self.data_collector.album_pk, 1)

#
# class VerifyFramesManager(AlbumProcessingManager):
#     def run(self):
#         photos = Photos.objects.filter(album_id=self.data_collector.album_pk)
#         for photo in photos:
#             self._delete_wrong_data(photo)
#             self.redisAPI.renumber_faces_of_photo(photo.pk)
#             # self._set_correct_status()
#
#         faces_amount = self._count_verified_faces(photos)
#         if faces_amount == 0:
#             self.redisAPI.set_no_faces(self.data_collector.album_pk)
#             DataDeletionSupporter.clean_after_recognition(album_pk=self.data_collector.album_pk)
#             set_album_photos_processed(album_pk=self.data_collector.album_pk, status=True)
#         else:
#             self._start_celery_task(next_stage=self._get_next_stage())
#
#     def _delete_wrong_data(self, photo):
#         for face_number in self.data_collector.data[photo.slug]:
#             face_name = f"face_{face_number}"
#             self.redisAPI.del_face(photo.pk, face_name)
#
#     def _count_verified_faces(self, photos):
#         count = 0
#         for pk in map(lambda p: p.pk, photos):
#             if self.redisAPI.is_face_in_photo(photo_pk=pk, face_index=1):
#                 count += 1
#         return count
