import os
import redis
import face_recognition as fr
import pickle
from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos

from photoalbums.settings import REDIS_HOST, REDIS_PORT, BASE_DIR

redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)


class ZeroStageHandler:
    """Class for handle automatic finding faces on album's photos."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._path = self._prepare_path()

    def handle(self):
        for photo in Photos.objects.filter(album__pk=self._album_pk, is_private=False):
            image = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))
            faces = self._find_faces_on_image(image=image)
            self._print_photo_with_framed_faces(image=image, faces=faces, pk=photo.pk)
            self._save_photo_data(data=faces, pk=photo.pk)

        self._save_album_report()

    def _prepare_path(self):
        path = os.path.join(BASE_DIR, 'media/temp_photos', f'album_{self._album_pk}')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @staticmethod
    def _find_faces_on_image(image):
        face_locs = fr.face_locations(image)
        face_encs = fr.face_encodings(image)
        faces = [(location, encoding) for (location, encoding) in zip(face_locs, face_encs)]
        return faces

    def _print_photo_with_framed_faces(self, image, faces, pk):
        pil_image = Image.fromarray(image)
        draw = ImageDraw.Draw(pil_image)
        for i, (location, encoding) in enumerate(faces, 1):
            top, right, bottom, left = location
            draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=4)
            fontsize = (bottom - top) // 3
            font = ImageFont.truetype("arialbd.ttf", fontsize)
            draw.text((left, top), str(i), fill=(255, 0, 0), font=font)
        del draw
        pil_image.save(os.path.join(self._path, f"photo_{pk}.jpg"))

    def _save_photo_data(self, data, pk):
        for i, (location, encoding) in enumerate(data, 1):
            redis_instance.hset(f"photo_{pk}", f"face_{i}_location", pickle.dumps(location))
            redis_instance.hset(f"photo_{pk}", f"face_{i}_encoding", encoding.dumps())
        redis_instance.expire(f"photo_{pk}", 86_400)
        redis_instance.hincrby(f"album_{self._album_pk}", "number_of_processed_photos")

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 0)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{self._album_pk}", 86_400)
