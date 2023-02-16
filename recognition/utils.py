import pickle
import redis

from mainapp.models import Photos
from .models import Patterns
from .data_classes import FaceData, PatternData


from photoalbums.settings import REDIS_HOST, REDIS_PORT


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


def set_album_photos_processed(album_pk: int, status: bool):
    photos = Photos.objects.filter(album__pk=album_pk)
    for photo in photos:
        photo.faces_extracted = status

    Photos.objects.bulk_update(photos, ['faces_extracted'])


def recalculate_pattern_center(pattern: Patterns):
    faces = pattern.faces_set.select_related('photo').all()
    for i, face in enumerate(faces):
        face_data = FaceData(photo_pk=face.photo.pk,
                             index=face.index,
                             location=(face.loc_top, face.loc_right,
                                       face.loc_bot, face.loc_left),
                             encoding=pickle.loads(face.encoding))
        if i == 0:
            pattern_data = PatternData(face_data)
        else:
            pattern_data.add_face(face_data)

    pattern_data.find_central_face()
    for i, face_data in enumerate(pattern_data):
        if face_data == pattern_data.central_face:
            pattern.central_face = faces[i]
            pattern.save(update_fields=['central_face'])
            break
