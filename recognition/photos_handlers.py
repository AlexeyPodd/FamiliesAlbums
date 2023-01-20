import os
import re

import redis
import face_recognition as fr
import pickle
from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos, Albums
from photoalbums.settings import REDIS_HOST, REDIS_PORT, BASE_DIR, REDIS_DATA_EXPIRATION_SECONDS, \
    FACE_RECOGNITION_TOLERANCE, PATTERN_EQUALITY_TOLERANCE, MEDIA_ROOT

from .data_classes import *
from .models import People, Patterns, Faces


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


class FaceSearchingHandler:
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
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/frames')
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
        i = 0
        for i, (location, encoding) in enumerate(data, 1):
            redis_instance.hset(f"photo_{pk}", f"face_{i}_location", pickle.dumps(location))
            redis_instance.hset(f"photo_{pk}", f"face_{i}_encoding", encoding.dumps())
        redis_instance.hset(f"photo_{pk}", "faces_amount", i)
        redis_instance.expire(f"photo_{pk}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hincrby(f"album_{self._album_pk}", "number_of_processed_photos")

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 1)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.hset(f"album_{self._album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class RelateFacesHandler:
    """Class for automatic joining founded faces into patterns."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._path = self._prepare_path()
        self._queryset = Photos.objects.filter(album__pk=self._album_pk, is_private=False)
        self._patterns = []
        self._data = {}

    def handle(self):
        self._get_faces_data_from_redis()
        self._relate_faces_data()
        self._save_patterns_data_to_redis()
        self._print_pattern_faces()
        self._save_album_report()

    def _get_faces_data_from_redis(self):
        for photo in self._queryset:
            faces_amount = int(redis_instance.hget(f"photo_{photo.pk}", f"faces_amount"))
            photo_faces = [FaceData(photo.pk, i,
                                    pickle.loads(redis_instance_raw.hget(f"photo_{photo.pk}", f"face_{i}_location")),
                                    pickle.loads(redis_instance_raw.hget(f"photo_{photo.pk}", f"face_{i}_encoding"))) for i in range(1, faces_amount+1)]
            self._data.update({photo.pk: photo_faces})

    def _relate_faces_data(self):
        for photo_pk, faces in self._data.items():
            if not self._patterns:
                self._patterns.extend([PatternData(face) for face in faces])
            else:
                for face in faces:
                    # comparing with already added faces
                    for pattern in self._patterns:
                        pattern_encodings = [saved_face.encoding for saved_face in pattern]
                        if self._is_same_face(face.encoding, pattern_encodings):
                            pattern.add_face(face)
                            break
                    else:
                        self._patterns.append(PatternData(face))

    @staticmethod
    def _is_same_face(face_enc, known_encs):
        result_list = fr.compare_faces(known_encs, face_enc, FACE_RECOGNITION_TOLERANCE)
        return sum(result_list) / len(result_list) > PATTERN_EQUALITY_TOLERANCE

    def _save_patterns_data_to_redis(self):
        for i, pattern in enumerate(self._patterns, 1):
            for j, face in enumerate(pattern, 1):
                redis_instance.hset(f"album_{self._album_pk}_pattern_{i}",
                                    f"face_{j}",
                                    f"photo_{face.photo_pk}_face_{face.index}")

            redis_instance.hset(f"album_{self._album_pk}_pattern_{i}",
                                "faces_amount",
                                len(pattern))

    def _prepare_path(self):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self._album_pk}/patterns')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def _print_pattern_faces(self):
        images = {}
        for photo in self._queryset:
            images[photo.pk] = fr.load_image_file(os.path.join(BASE_DIR, photo.original.url[1:]))

        for i, pattern in enumerate(self._patterns, 1):
            for j, face in enumerate(pattern, 1):
                top, right, bottom, left = face.location
                face_image = images.get(face.photo_pk)[top:bottom, left:right]
                pil_image = Image.fromarray(face_image)
                if j == 1:
                    os.makedirs(os.path.join(self._path, str(i)))
                save_path = os.path.join(self._path, str(i), f'{j}.jpg')
                pil_image.save(save_path)

    def _save_album_report(self):
        redis_instance.hset(f"album_{self._album_pk}", "current_stage", 3)
        redis_instance.hset(f"album_{self._album_pk}", "status", "completed")
        redis_instance.expire(f"album_{self._album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class ComparingExistingAndNewPeopleHandler:
    """Class for handling uniting people of processing album with previously created people of this user."""

    def __init__(self, album_pk):
        self._album_pk = album_pk
        self._album = None
        self._existing_people = []
        self._people = []
        self._pairs = []

    def handle(self):
        self._get_existing_people_data_from_db()
        self._get_new_people_data_from_redis()
        if self._existing_people:
            self._unite_people()
        self._save_united_people_data_to_redis()

    def _get_existing_people_data_from_db(self):
        queryset = Faces.objects.filter(
            pattern__person__owner__username=self._album.owner.username
        ).select_related(
            'pattern__person', 'photo', 'pattern__central_face'
        ).exclude(
            photo__album__pk=self._album_pk
        ).order_by('pattern__person', 'pattern')

        # Extracting data from db_instances
        person_db_instance = pattern_db_instance = None
        person = pattern = None
        for face_db_instance in queryset:
            face = FaceData(photo_pk=face_db_instance.photo.pk,
                            index=face_db_instance.index,
                            location=(face_db_instance.loc_top, face_db_instance.loc_right,
                                      face_db_instance.loc_bot, face_db_instance.loc_left),
                            encoding=pickle.loads(face_db_instance.encoding))

            if person_db_instance != face_db_instance.pattern.person:
                person_db_instance = face_db_instance.pattern.person
                person = PersonData()
                self._existing_people.append(person)

            if pattern_db_instance != face_db_instance.pattern:
                pattern_db_instance = face_db_instance.pattern
                pattern = PatternData(face)
                person.add_pattern(pattern)
            else:
                pattern.add_face(face)

            if face_db_instance.pk == face_db_instance.pattern.central_face.pk:
                pattern.center = face

    def _get_new_people_data_from_redis(self):
        i = 1
        while redis_instance.exists(f"album_{self._album_pk}_person_{i}"):
            person = PersonData()

            j = 1
            while redis_instance.hexists(f"album_{self._album_pk}_person_{i}", f"pattern_{j}"):
                pattern_ind = int(redis_instance.hget(f"album_{self._album_pk}_person_{i}", f"pattern_{j}"))

                for k in range(1, int(redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}",
                                                          "faces_amount")) + 1):
                    face_address = redis_instance.hget(f"album_{self._album_pk}_pattern_{pattern_ind}", f"face{k}")
                    photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
                    face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
                    face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
                    face = FaceData(photo_pk=int(photo_pk),
                                    index=int(face_ind),
                                    location=face_loc,
                                    encoding=face_enc)
                    if k == 1:
                        pattern = PatternData(face)
                    else:
                        pattern.add_face(face)

                pattern.find_central_face()
                person.add_pattern(pattern)

            self._people.append(person)
