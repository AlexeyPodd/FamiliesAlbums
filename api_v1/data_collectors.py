from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus, RedisAPIFinished


class RecognitionStateCollector:
    """Base cass for collecting data of album processing."""

    def __init__(self, album_pk: int, validated_data=None):
        self.album_pk = album_pk
        self.stage = RedisAPIStage.get_stage(album_pk)
        self.status = RedisAPIStatus.get_status(album_pk)
        self.finished = RedisAPIFinished.get_finished_status(album_pk)
        self.data = validated_data

    def collect(self):
        pass
