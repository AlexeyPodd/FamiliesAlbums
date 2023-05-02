import pickle
import re
from typing import List, Tuple
import redis

from django.http import Http404

from photoalbums.settings import REDIS_DATA_EXPIRATION_SECONDS
from ..data_classes import FaceData, PatternData, PersonData
from photoalbums.settings import REDIS_HOST, REDIS_PORT


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


class RedisAPIStage:
    @staticmethod
    def set_stage(album_pk: int, stage: int):
        if stage not in range(-1, 10):
            raise ValueError("Unsupported stage value")

        redis_instance.hset(f"album_{album_pk}", "current_stage", stage)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_stage(album_pk: int):
        stage = redis_instance.hget(f"album_{album_pk}", "current_stage")
        if stage is not None:
            stage = int(stage)
        return stage

    @classmethod
    def get_stage_or_404(cls, album_pk: int):
        stage = cls.get_stage(album_pk)
        if stage is None:
            raise Http404
        return stage


class RedisAPIStatus:
    @staticmethod
    def set_status(album_pk: int, status: str):
        if status not in ("processing", "completed"):
            raise ValueError("status should be \"processing\" or \"completed\"")

        redis_instance.hset(f"album_{album_pk}", "status", status)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_status(album_pk: int):
        return redis_instance.hget(f"album_{album_pk}", "status")

    @classmethod
    def get_status_or_completed(cls, album_pk: int):
        if redis_instance.hexists(f"album_{album_pk}", "current_stage"):
            return cls.get_status(album_pk)
        else:
            return 'completed'


class RedisAPIFinished:
    @staticmethod
    def set_no_faces(album_pk: int):
        redis_instance.set(f"album_{album_pk}_finished", "no_faces")
        redis_instance.expire(f"album_{album_pk}_finished", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_finished(album_pk: int):
        redis_instance.set(f"album_{album_pk}_finished", 1)
        redis_instance.expire(f"album_{album_pk}_finished", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_finished_status(album_pk: int):
        return redis_instance.get(f"album_{album_pk}_finished")


class RedisAPIProcessedPhotos:
    @staticmethod
    def get_processed_photos_amount(album_pk: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}", "number_of_processed_photos"))
        except TypeError:
            return 0

    @staticmethod
    def reset_processed_photos_amount(album_pk: int):
        redis_instance.hset(f"album_{album_pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def register_photo_processed(album_pk: int):
        redis_instance.hincrby(f"album_{album_pk}", "number_of_processed_photos")
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class RedisAPIPhotoDataGetter:
    @staticmethod
    def get_face_locations_in_photo(photo_pk: int):
        faces_locations = []
        i = 1
        while redis_instance.hexists(f"photo_{photo_pk}", f"face_{i}_location"):
            faces_locations.append(pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_location")))
            i += 1
        return faces_locations

    @staticmethod
    def get_faces_data_of_photo(photo_pk: int):
        faces_amount = int(redis_instance.hget(f"photo_{photo_pk}", "faces_amount"))
        photo_faces = [FaceData(photo_pk, i,
                                pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_location")),
                                pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_encoding")))
                       for i in range(1, faces_amount + 1)]
        return photo_faces

    @staticmethod
    def get_single_photo_with_one_face(photos_pks):
        photo_pk_with_face = None
        for pk in photos_pks:
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                if photo_pk_with_face is None:
                    photo_pk_with_face = pk
                else:
                    raise Exception("Was founded multiple faces. Need relate them before saving.")

        return photo_pk_with_face

    @staticmethod
    def get_faces_amount_in_photo(photo_pk: int):
        return int(redis_instance.hget(f"photo_{photo_pk}", "faces_amount"))


class RedisAPIPhotoDataSetter:
    @staticmethod
    def set_photo_faces_data(album_pk: int, photo_pk: int, data: List[Tuple]):
        i = 0
        for i, (location, encoding) in enumerate(data, 1):
            redis_instance.hset(f"photo_{photo_pk}", f"face_{i}_location", pickle.dumps(location))
            redis_instance.hset(f"photo_{photo_pk}", f"face_{i}_encoding", encoding.dumps())
        redis_instance.hset(f"photo_{photo_pk}", "faces_amount", i)
        redis_instance.expire(f"photo_{photo_pk}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hincrby(f"album_{album_pk}", "number_of_processed_photos")
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def renumber_faces_of_photo(photo_pk):
        faces_amount = RedisAPIPhotoDataGetter.get_faces_amount_in_photo(photo_pk)
        count = 0
        for i in range(1, faces_amount + 1):
            if RedisAPIPhotoDataChecker.is_face_in_photo(photo_pk, i):
                count += 1
                if count != i:
                    redis_instance.hset(f"photo_{photo_pk}",
                                        f"face_{count}_location",
                                        redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_location"))
                    redis_instance.hdel(f"photo_{photo_pk}", f"face_{i}_location")
                    redis_instance.hset(f"photo_{photo_pk}",
                                        f"face_{count}_encoding",
                                        redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{i}_encoding"))
                    redis_instance.hdel(f"photo_{photo_pk}", f"face_{i}_encoding")

        redis_instance.hset(f"photo_{photo_pk}", "faces_amount", count)
        redis_instance.expire(f"photo_{photo_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def del_face(photo_pk: int, face_name: str):
        redis_instance.hdel(f"photo_{photo_pk}", face_name + "_location", face_name + "_encoding")
        redis_instance.expire(f"photo_{photo_pk}", REDIS_DATA_EXPIRATION_SECONDS)


class RedisAPIPhotoDataChecker:
    @staticmethod
    def is_face_in_photo(photo_pk: int, face_index: int):
        return redis_instance.hexists(f"photo_{photo_pk}", f"face_{face_index}_location")


class RedisAPIPhotoSlug:
    @staticmethod
    def set_photos_slugs(album_pk: int, photos_slugs: List[str]):
        redis_instance.rpush(f"album_{album_pk}_photos", *photos_slugs)
        redis_instance.expire(f"album_{album_pk}_photos", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_first_photo_slug(album_pk: int):
        return redis_instance.lindex(f"album_{album_pk}_photos", 0)

    @staticmethod
    def get_last_photo_slug(album_pk: int):
        return redis_instance.lindex(f"album_{album_pk}_photos", -1)

    @staticmethod
    def get_next_photo_slug(album_pk: int, current_photo_slug: str):
        return redis_instance.lindex(f"album_{album_pk}_photos",
                                     redis_instance.lpos(f"album_{album_pk}_photos", current_photo_slug) + 1)

    @staticmethod
    def delete_photo_slug(album_pk: int, photo_slug: str):
        redis_instance.lrem(f"album_{album_pk}_photos", 1, photo_slug)
        redis_instance.expire(f"album_{album_pk}_photos", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def get_photo_slugs_amount(album_pk: int):
        return redis_instance.llen(f"album_{album_pk}_photos")


class RedisAPIPatternDataSetter:
    @staticmethod
    def set_pattern_faces_amount(album_pk: int, pattern_index: int, faces_amount: int):
        redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount", faces_amount)
        redis_instance.expire(f"album_{album_pk}_pattern_{pattern_index}", REDIS_DATA_EXPIRATION_SECONDS)

    @classmethod
    def set_patterns_data(cls, album_pk: int, patterns: List[PatternData]):
        for i, pattern in enumerate(patterns, 1):
            for j, face in enumerate(pattern, 1):
                redis_instance.hset(f"album_{album_pk}_pattern_{i}",
                                    f"face_{j}",
                                    f"photo_{face.photo_pk}_face_{face.index}")
                if face is pattern.central_face:
                    redis_instance.hset(f"album_{album_pk}_pattern_{i}",
                                        "central_face",
                                        f"face_{j}")
            cls.set_pattern_faces_amount(album_pk, pattern_index=i, faces_amount=len(pattern))

    @staticmethod
    def move_face_data(album_pk: int, face_name: str, from_pattern: int, to_pattern: int):
        face_data = redis_instance.hget(f"album_{album_pk}_pattern_{from_pattern}", face_name)
        redis_instance.hset(f"album_{album_pk}_pattern_{to_pattern}",
                            face_name,
                            face_data)
        redis_instance.hdel(f"album_{album_pk}_pattern_{from_pattern}", face_name)
        redis_instance.expire(f"album_{album_pk}_pattern_{to_pattern}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{album_pk}_pattern_{from_pattern}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def renumber_faces_in_patterns(album_pk: int, pattern_index: int, faces_amount: int):
        count = 0
        for j in range(1, faces_amount + 1):
            if RedisAPIPatternDataChecker.is_face_in_pattern(album_pk, face_index=j, pattern_index=pattern_index):
                count += 1
                if count != j:
                    # Renumbering data keys in redis
                    redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}",
                                        f"face_{count}",
                                        redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}",
                                                            f"face_{j}"))
                    redis_instance.hdel(f"album_{album_pk}_pattern_{pattern_index}", f"face_{j}")

        redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount", count)
        redis_instance.expire(f"album_{album_pk}_pattern_{pattern_index}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def recalculate_pattern_center(album_pk: int, pattern_index: int):
        # Get data from redis
        for i in range(1, int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}",
                                                  "faces_amount")) + 1):
            face_address = redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}", f"face_{i}")
            photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
            face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
            face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
            face = FaceData(photo_pk=int(photo_pk),
                            index=int(face_ind),
                            location=face_loc,
                            encoding=face_enc)
            if i == 1:
                pattern = PatternData(face)
            else:
                pattern.add_face(face)

        # Calculate center of pattern
        pattern.find_central_face()

        # Set central face to redis
        for i, face in enumerate(pattern, 1):
            if face is pattern.central_face:
                redis_instance.hset(f"album_{album_pk}_pattern_{pattern_index}", "central_face", f"face_{i}")
                redis_instance.expire(f"album_{album_pk}_pattern_{pattern_index}", REDIS_DATA_EXPIRATION_SECONDS)
                break

    @staticmethod
    def set_single_face_central(album_pk: int, total_patterns_amount: int, skip: int):
        for i in range(skip + 1, total_patterns_amount + 1):
            redis_instance.hset(f"album_{album_pk}_pattern_{i}", "central_face", "face_1")
            redis_instance.expire(f"album_{album_pk}_pattern_{i}", REDIS_DATA_EXPIRATION_SECONDS)


class RedisAPIPatternDataGetter:
    @staticmethod
    def get_pattern_faces_amount(album_pk: int, pattern_index: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_index}", "faces_amount"))
        except TypeError:
            return 0


class RedisAPIPatternDataChecker:
    @staticmethod
    def is_face_in_pattern(album_pk: int, face_index: int, pattern_index: int):
        return redis_instance.hexists(f"album_{album_pk}_pattern_{pattern_index}", f"face_{face_index}")


class RedisAPIFullAlbumPeopleDataGetter:
    @staticmethod
    def get_face_data(album_pk: int, pattern_ind: int, face_ind_in_pattern: int):
        face_address = redis_instance.hget(f"album_{album_pk}_pattern_{pattern_ind}", f"face_{face_ind_in_pattern}")
        photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
        face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
        face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
        face_data = FaceData(photo_pk=int(photo_pk),
                             index=int(face_ind),
                             location=face_loc,
                             encoding=face_enc)
        return face_data

    @classmethod
    def get_pattern_data(cls, album_pk: int, pattern_ind: int, pattern_central_face_ind: int):
        for k in range(1, int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_ind}", "faces_amount")) + 1):
            face_data = cls.get_face_data(album_pk=album_pk, pattern_ind=pattern_ind, face_ind_in_pattern=k)
            if k == 1:
                pattern_data = PatternData(face_data)
            else:
                pattern_data.add_face(face_data)

            if k == pattern_central_face_ind:
                pattern_data.central_face = face_data

        return pattern_data

    @classmethod
    def get_person_data(cls, album_pk: int, person_ind: int, pair_pk):
        person_data = PersonData(redis_indx=person_ind, pair_pk=pair_pk)
        j = 1
        while redis_instance.hexists(f"album_{album_pk}_person_{person_ind}", f"pattern_{j}"):
            pattern_ind = int(redis_instance.hget(f"album_{album_pk}_person_{person_ind}", f"pattern_{j}"))
            pattern_ccentral_face_ind = int(redis_instance.hget(f"album_{album_pk}_pattern_{pattern_ind}",
                                                                "central_face")[5:])
            pattern_data = cls.get_pattern_data(album_pk=album_pk, pattern_ind=pattern_ind,
                                                pattern_central_face_ind=pattern_ccentral_face_ind)
            person_data.add_pattern(pattern_data)
            j += 1
        return person_data

    @classmethod
    def get_people_data(cls, album_pk: int):
        people_data = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                pair_pk = int(redis_instance.hget(f"album_{album_pk}_person_{i}", "real_pair")[7:])
            else:
                pair_pk = None
            person_data = cls.get_person_data(album_pk=album_pk, person_ind=i, pair_pk=pair_pk)
            people_data.append(person_data)
            i += 1

        return people_data


class RedisAPIAlbumDataGetter:
    @staticmethod
    def get_album_faces_amounts(album_pk: int):
        amounts = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_pattern_{i}"):
            amounts.append(RedisAPIPatternDataGetter.get_pattern_faces_amount(album_pk, i))
            i += 1
        return tuple(amounts)

    @staticmethod
    def get_verified_patterns_amount(album_pk: int):
        try:
            return int(redis_instance.hget(f"album_{album_pk}", "number_of_verified_patterns"))
        except TypeError:
            return 0

    @staticmethod
    def get_indexes_of_single_patterns(album_pk):
        single_patterns = []
        for x in range(1, int(redis_instance.hget(f"album_{album_pk}", "number_of_verified_patterns")) + 1):
            if not redis_instance.hexists(f"album_{album_pk}_pattern_{x}", "person"):
                single_patterns.append(x)
        return tuple(single_patterns)

    @staticmethod
    def encrease_and_get_people_amount(album_pk: int):
        redis_instance.hincrby(f"album_{album_pk}", "people_amount")
        return redis_instance.hget(f"album_{album_pk}", "people_amount")

    @staticmethod
    def get_first_patterns_indexes_of_people(album_pk: int, people_indexes: List[int]):
        return [redis_instance.hget(f"album_{album_pk}_person_{x}", "pattern_1") for x in people_indexes]


class RedisAPIAlbumDataSetter:
    @staticmethod
    def register_verified_patterns(album_pk: int, amount: int):
        redis_instance.hset(f"album_{album_pk}", "number_of_verified_patterns", amount)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def clear_redis_album_data(album_pk: int, finished: bool, photo_pks: List[int]):
        if not finished:
            redis_instance.hdel(f"album_{album_pk}", "number_of_processed_photos",
                                "number_of_verified_patterns", "people_amount")
            redis_instance.delete(f"album_{album_pk}_finished")
        else:
            redis_instance.delete(f"album_{album_pk}")
        redis_instance.delete(f"album_{album_pk}_photos")
        redis_instance.delete(*[f"photo_{pk}" for pk in photo_pks])

        str_patterns = (f"album_{album_pk}_pattern_", f"album_{album_pk}_person_")
        for str_pattern in str_patterns:
            i = 1
            while redis_instance.exists(str_pattern + str(i)):
                redis_instance.delete(str_pattern + str(i))
                i += 1


class RedisAPIAlbumDataChecker:
    @staticmethod
    def check_any_person_found(album_pk: int):
        return redis_instance.exists(f"album_{album_pk}_person_1")

    @staticmethod
    def check_single_pattern_formed(album_pk: int):
        return redis_instance.exists(f"album_{album_pk}_pattern_1") and \
            not redis_instance.exists(f"album_{album_pk}_pattern_2")

    @staticmethod
    def check_album_in_processing(temp_dir_name):
        return redis_instance.exists(temp_dir_name)


class RedisAPIPersonDataCreator:
    @staticmethod
    def create_person_from_single_pattern(album_pk: int):
        person_data = PersonData(redis_indx=1)
        pattern_central_face_ind = int(redis_instance.hget(f"album_{album_pk}_pattern_1", "central_face")[5:])
        pattern_data = RedisAPIFullAlbumPeopleDataGetter.get_pattern_data(
            album_pk=album_pk,
            pattern_ind=1,
            pattern_central_face_ind=pattern_central_face_ind
        )
        person_data.add_pattern(pattern_data)
        return person_data

    @staticmethod
    def create_person_from_single_face(photo_pk):
        person_data = PersonData(redis_indx=1)
        face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_location"))
        face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_1_encoding"))
        face = FaceData(photo_pk=int(photo_pk),
                        index=1,
                        location=face_loc,
                        encoding=face_enc)
        pattern_data = PatternData(face)
        person_data.add_pattern(pattern_data)
        return person_data


class RedisAPIPersonDataSetter:
    @classmethod
    def set_one_person_with_one_pattern_with_one_face(cls, album_pk: int, photo_pk: int):
        redis_instance.hset(f"album_{album_pk}_pattern_1", "face_1", f"photo_{photo_pk}_face_1")
        redis_instance.hset(f"album_{album_pk}_pattern_1", "central_face", "face_1")
        redis_instance.hset(f"album_{album_pk}_pattern_1", "faces_amount", "1")
        redis_instance.hset(f"album_{album_pk}_pattern_1", "person", "1")
        redis_instance.hset(f"album_{album_pk}", "number_of_verified_patterns", "1")
        redis_instance.expire(f"album_{album_pk}_pattern_1", REDIS_DATA_EXPIRATION_SECONDS)
        cls.set_one_person_with_one_pattern(album_pk=album_pk)

    @staticmethod
    def set_one_person_with_one_pattern(album_pk: int):
        redis_instance.hset(f"album_{album_pk}_person_1", "pattern_1", "1")
        redis_instance.hset(f"album_{album_pk}", "people_amount", "1")
        redis_instance.expire(f"album_{album_pk}_person_1", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{album_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_pattern_to_person(album_pk: int, pattern_name: str,
                              pattern_number_in_person: (int, str), person_number: (int, str)):
        redis_instance.hset(f"album_{album_pk}_{pattern_name}", "person", person_number)
        redis_instance.expire(f"album_{album_pk}_{pattern_name}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.hset(f"album_{album_pk}_person_{person_number}",
                            f"pattern_{pattern_number_in_person}", pattern_name[8:])
        redis_instance.expire(f"album_{album_pk}_person_{person_number}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_created_person(album_pk: int, pattern_name: str):
        redis_instance.hincrby(f"album_{album_pk}", "people_amount")
        new_person_number = redis_instance.hget(f"album_{album_pk}", "people_amount")

        redis_instance.hset(f"album_{album_pk}_{pattern_name}", "person", new_person_number)
        redis_instance.hset(f"album_{album_pk}_person_{new_person_number}",
                            f"pattern_1", pattern_name[8:])
        redis_instance.expire(f"album_{album_pk}_{pattern_name}", REDIS_DATA_EXPIRATION_SECONDS)
        redis_instance.expire(f"album_{album_pk}_person_{new_person_number}",
                              REDIS_DATA_EXPIRATION_SECONDS)


class RedisAPIMatchesGetter:
    @staticmethod
    def get_matching_people(album_pk: int):
        old_people_pks = []
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "tech_pair"):
                pk = int(redis_instance.hget(f"album_{album_pk}_person_{i}", "tech_pair")[7:])
                old_people_pks.append(pk)
                new_people_inds.append(i)
            i += 1

        return old_people_pks, new_people_inds

    @staticmethod
    def get_old_paired_people(album_pk: int):
        paired = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{album_pk}_person_{i}", "real_pair")[7:]))
            i += 1
        return paired

    @staticmethod
    def get_new_unpaired_people(album_pk: int):
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                new_people_inds.append(i)
            i += 1

        patt_inds = [redis_instance.hget(f"album_{album_pk}_person_{x}", "pattern_1") for x in new_people_inds]
        face_urls = [f"/media/temp_photos/album_{album_pk}/patterns/{x}/1.jpg" for x in patt_inds]

        return tuple(zip(new_people_inds, face_urls))

    @staticmethod
    def get_old_paired_people_pks(album_pk: int):
        paired = []
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{album_pk}_person_{i}", "real_pair")[7:]))
            i += 1
        return paired


class RedisAPIMatchesSetter:
    @staticmethod
    def set_matching_people(album_pk: int, pairs: List[Tuple[PersonData, PersonData]]):
        for old_per, new_per in pairs:
            redis_instance.hset(f"album_{album_pk}_person_{new_per.redis_indx}",
                                "tech_pair", f"person_{old_per.pk}")

    @staticmethod
    def set_verified_pair(album_pk: int, new_per_ind, old_per_pk):
        redis_instance.hset(f"album_{album_pk}_person_{new_per_ind}", "real_pair", f"person_{old_per_pk}")

    @staticmethod
    def set_new_pair(album_pk: int, new_person_ind: int, old_person_pk: int):
        redis_instance.hset(f'album_{album_pk}_person_{new_person_ind}', 'real_pair', f'person_{old_person_pk}')
        redis_instance.expire(f'album_{album_pk}_person_{new_person_ind}', REDIS_DATA_EXPIRATION_SECONDS)


class RedisAPIMatchesChecker:
    @staticmethod
    def check_any_tech_matches(album_pk: int):
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if redis_instance.hexists(f"album_{album_pk}_person_{i}", "tech_pair"):
                return True
            i += 1
        else:
            return False

    @staticmethod
    def check_existing_new_single_people(album_pk: int):
        i = 1
        while redis_instance.exists(f"album_{album_pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{album_pk}_person_{i}", "real_pair"):
                return True
            i += 1
        else:
            return False


class RedisAPISearchGetter:
    @staticmethod
    def get_founded_similar_people(person_pk):
        return list(map(int, redis_instance.lrange(f"nearest_people_to_{person_pk}", 0, -1)))

    @staticmethod
    def get_searched_patterns_amount(person_pk):
        return int(redis_instance.get(f"person_{person_pk}_processed_patterns_amount"))


class RedisAPISearchSetter:
    @staticmethod
    def encrease_patterns_search_amount(person_pk):
        redis_instance.incrby(f"person_{person_pk}_processed_patterns_amount")
        redis_instance.expire(f"person_{person_pk}_processed_patterns_amount", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def set_founded_similar_people(person_pk, pks):
        redis_instance.rpush(f"nearest_people_to_{person_pk}", *pks)
        redis_instance.delete(f"person_{person_pk}_processed_patterns_amount")
        redis_instance.expire(f"nearest_people_to_{person_pk}", REDIS_DATA_EXPIRATION_SECONDS)

    @staticmethod
    def prepare_to_search(person_pk):
        redis_instance.delete(f"nearest_people_to_{person_pk}")
        redis_instance.set(f"person_{person_pk}_processed_patterns_amount", 0)
        redis_instance.expire(f"person_{person_pk}_processed_patterns_amount", REDIS_DATA_EXPIRATION_SECONDS)
