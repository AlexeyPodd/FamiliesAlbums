from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus
from recognition.tasks import recognition_task


class AlbumProcessingManage:
    def __init__(self, data_collector):
        self.data_collector = data_collector

    def run(self):
        raise NotImplementedError


class AlbumProcessStartManager(AlbumProcessingManage):
    def run(self):
        RedisAPIStage.set_stage(album_pk=self.data_collector.album_pk, stage=0)
        RedisAPIStatus.set_status(album_pk=self.data_collector.album_pk, status="processing")
        recognition_task.delay(self.data_collector.album_pk, 1)
