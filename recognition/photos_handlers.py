import os
import redis
import face_recognition as fr
import pickle
from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos

from photoalbums.settings import REDIS_HOST, REDIS_PORT, BASE_DIR

redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0)


class ZeroStageHandler:
    def __init__(self, album_pk):
        self.album_pk = album_pk
        self.photos = {}

    def handle(self):
        self._load_photos()
        self._find_faces()
        self._print_temp_photos_with_frames()

    def _load_photos(self):
        for photo in Photos.objects.filter(album__pk=self.album_pk):
            self.photos[photo.pk] = {"image": fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))}

    def _find_faces(self):
        for pk, data in self.photos.items():
            face_locs = fr.face_locations(data.get("image"))
            face_encs = fr.face_encodings(data.get("image"))
            self.photos[pk]["faces"] = [(location, encoding) for (location, encoding) in zip(face_locs, face_encs)]

    def _print_temp_photos_with_frames(self):
        path = os.path.join(BASE_DIR, 'media/temp_photos', f'album_{self.album_pk}')
        if not os.path.exists(path):
            os.makedirs(path)

        for pk, data in self.photos.items():
            pil_image = Image.fromarray(data.get("image"))
            draw = ImageDraw.Draw(pil_image)

            for i, (location, encoding) in enumerate(data.get("faces"), 1):
                top, right, bottom, left = location
                draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=4)

                fontsize = (bottom - top) // 3
                font = ImageFont.truetype("arialbd.ttf", fontsize)
                draw.text((left, top), str(i), fill=(255, 0, 0), font=font)

            del draw
            pil_image.save(os.path.join(path, f"photo_{pk}.jpg"))

    def save_data_to_redis(self):
        redis_instance.hset(f"album_{self.album_pk}", "current_stage", 0)
        redis_instance.expire(f"album_{self.album_pk}", 86_400)

        for pk, data in self.photos.items():
            for location, encoding in data.get("faces"):
                redis_instance.hset(f"photo_{pk}", pickle.dumps(location), encoding.dumps())
            redis_instance.expire(f"photo_{pk}", 86_400)
