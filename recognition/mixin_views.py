from photoalbums.settings import REDIS_DATA_EXPIRATION_SECONDS
from .utils import redis_instance
from .tasks import recognition_task


class RecognitionMixin:
    @staticmethod
    def _set_no_faces_and_clear(album_pk: int):
        redis_instance.set(f"album_{album_pk}_finished", "no_faces")
        redis_instance.expire(f"album_{album_pk}_finished", REDIS_DATA_EXPIRATION_SECONDS)
        recognition_task.delay(album_pk, -1)
