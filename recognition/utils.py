import os
import redis

from django.forms import BooleanField

from mainapp.models import Photos
from photoalbums.settings import MEDIA_ROOT, REDIS_HOST, REDIS_PORT
from .models import Faces, People, Patterns


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


class VerifyMatchField(BooleanField):
    def __init__(self, new_per_img, old_per_img, *args, **kwargs):
        self.new_per_img = new_per_img
        self.old_per_img = old_per_img
        super().__init__(*args, **kwargs)


class RecognitionSupporter:
    @classmethod
    def prepare_to_recognition(cls, album_pk):
        cls._clear_redis_album_data(album_pk)
        cls._clear_temp_files(album_pk)
        cls._clear_db_album_data(album_pk)
        cls._prepare_path(album_pk)

    @classmethod
    def clean_after_recognition(cls, album_pk):
        cls._clear_redis_album_data(album_pk)
        cls._clear_temp_files(album_pk)

    @staticmethod
    def _clear_redis_album_data(album_pk):
        if redis_instance.hget(f"album_{album_pk}", "current_stage") == '0':
            redis_instance.hdel(f"album_{album_pk}", "number_of_processed_photos",
                                "number_of_verified_patterns", "people_amount")
        else:
            redis_instance.delete(f"album_{album_pk}")
        redis_instance.delete(f"album_{album_pk}_photos")
        redis_instance.delete(*[f"photo_{photo.pk}" for photo in Photos.objects.filter(album__pk=album_pk)])

        str_patterns = (f"album_{album_pk}_pattern_", f"album_{album_pk}_person_")
        for str_pattern in str_patterns:
            i = 1
            while redis_instance.exists(str_pattern + str(i)):
                redis_instance.delete(str_pattern + str(i))
                i += 1

    @staticmethod
    def _clear_temp_files(album_pk):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{album_pk}')
        if os.path.exists(path):
            os.system(f'rm -rf {path}')

    @staticmethod
    def _clear_db_album_data(album_pk):
        album_faces = Faces.objects.filter(photo__album__pk=album_pk).select_related('pattern__person')
        related_patterns_pks = set(map(lambda f: f.pattern.pk, album_faces))
        related_people_pks = set(map(lambda f: f.pattern.person.pk, album_faces))

        album_faces.delete()
        Patterns.objects.filter(pk__in=related_patterns_pks,
                                faces__isnull=True).delete()
        People.objects.filter(pk__in=related_people_pks,
                              patterns__isnull=True).delete()

    @staticmethod
    def _prepare_path(album_pk):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{album_pk}/frames')
        if not os.path.exists(path):
            os.makedirs(path)


def set_album_photos_processed(album_pk: int, status: bool):
    photos = Photos.objects.filter(album__pk=album_pk)
    for photo in photos:
        photo.faces_extracted = status

    Photos.objects.bulk_update(photos, ['faces_extracted'])
