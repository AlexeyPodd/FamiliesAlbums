import re

from rest_framework import serializers

from mainapp.models import Photos
from recognition.models import People
from recognition.redis_interface.functional_api import RedisAPIPhotoSlug, RedisAPIPhotoDataGetter, \
    RedisAPIPatternDataGetter, RedisAPIPatternDataChecker, RedisAPIMatchesGetter, RedisAPIPersonDataChecker
from .mixins import AlbumProcessingMixin


# Precompiling regexes for validating data keys
pair_regex = re.compile(r'pair_[1-9][0-9]*')
person_regex = re.compile(r'person_[1-9][0-9]*')
pattern_regex = re.compile(r'pattern_[1-9][0-9]*')
face_regex = re.compile(r'face_[1-9][0-9]*')


# Serializer for GET requests
class AlbumProcessingInfoSerializer(serializers.Serializer):
    stage = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    finished = serializers.CharField(read_only=True)
    data = serializers.ReadOnlyField()


# Serializers below are for POST requests
# ----------------------------------------------------------------------------------------------------------------------
class StartAlbumProcessingSerializer(AlbumProcessingMixin, serializers.Serializer):
    start = serializers.BooleanField()

    def validate_start(self, value):
        if not value:
            raise serializers.ValidationError("start parameter must be set True.")
        return value

    def _check_relevance(self):
        if self.status == 'processing':
            raise serializers.ValidationError('Processing should be completed before starting over.')


class VerifyFramesSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 2
    photos_faces = serializers.DictField(
        allow_empty=False,
        child=serializers.ListField(child=serializers.IntegerField()),
    )

    def validate_photos_faces(self, data_dict):
        self._validate_photo_slugs(data_dict)
        self._make_unique_face_numbers(data_dict)
        self._validate_face_numbers(data_dict)
        return data_dict

    def _validate_photo_slugs(self, data_dict):
        slugs = set(data_dict.keys())
        redis_slugs = set(RedisAPIPhotoSlug.get_photo_slugs(self.album_pk))
        if slugs != redis_slugs:
            raise serializers.ValidationError("not all or invalid photo slugs")

    @staticmethod
    def _validate_face_numbers(data_dict):
        photo_slugs = tuple(data_dict.keys())
        photos = Photos.objects.filter(slug__in=photo_slugs)
        for photo in photos:
            face_numbers = data_dict[photo.slug]
            for face_number in face_numbers:
                if face_number < 1 or face_number > RedisAPIPhotoDataGetter.get_faces_amount_in_photo(photo.pk):
                    raise serializers.ValidationError(f"Invalid face number: {photo.slug} - {face_number}")

    @staticmethod
    def _make_unique_face_numbers(data_dict):
        for slug, face_numbers in data_dict.items():
            data_dict[slug] = list(set(face_numbers))


class VerifyPatternsSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 4
    patterns = serializers.DictField(
        allow_empty=False,
        child=serializers.ListField(
            allow_empty=False,
            child=serializers.ListField(
                allow_empty=False,
                child=serializers.CharField(),
            ),
        ),
    )

    def validate_patterns(self, data_dict):
        self._validate_patterns_names(data_dict)
        self._validate_faces_names(data_dict)
        return data_dict

    def _validate_patterns_names(self, data_dict):
        for pattern_name in data_dict.keys():
            if not re.fullmatch(pattern_regex, pattern_name):
                raise serializers.ValidationError(f"Invalid pattern name: {pattern_name}")

            if not RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, int(pattern_name[8:])):
                raise serializers.ValidationError(f"Pattern {pattern_name} does not exist or invalid")

        if RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, len(data_dict) + 1):
            raise serializers.ValidationError("Not all patterns data received")

    def _validate_faces_names(self, data_dict):
        for pattern_name, separated_faces_list in data_dict.items():
            faces_names = [face_name for lst in separated_faces_list for face_name in lst]
            for face_name in faces_names:
                if not re.fullmatch(face_regex, face_name):
                    raise serializers.ValidationError(f"Invalid face name: {face_name}")

            max_face_number = max(map(lambda s: int(s[5:]), faces_names))

            # Validating uniqueness and correct numbering
            if not len(faces_names) == len(set(faces_names)) == max_face_number:
                raise serializers.ValidationError("Improper faces numbering")

            # Validating existence of faces and amount
            pattern_index = int(pattern_name[8:])
            if not RedisAPIPatternDataChecker.is_face_in_pattern(self.album_pk, max_face_number, pattern_index) or \
                    RedisAPIPatternDataChecker.is_face_in_pattern(self.album_pk, max_face_number + 1, pattern_index):
                raise serializers.ValidationError(f"Wrong number of faces in {pattern_name}")


class GroupPatternsSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 5
    people_patterns = serializers.ListField(
        allow_empty=False,
        child=serializers.ListField(
            allow_empty=False,
            child=serializers.CharField(),
        ),
    )

    def validate_people_patterns(self, lst):
        pattern_list = [pattern for group in lst for pattern in group]
        for pattern_name in pattern_list:
            if not re.fullmatch(pattern_regex, pattern_name):
                raise serializers.ValidationError(f"Invalid pattern name: {pattern_name}")

        pattern_list.sort(key=lambda p: int(p[8:]))
        max_pattern_ind = int(pattern_list[-1][8:])

        # Validating uniqueness and correct numbering
        if not len(pattern_list) == len(set(pattern_list)) == max_pattern_ind:
            raise serializers.ValidationError("Improper pattern numbering")

        # Validating existence and amount of patterns
        if not RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, max_pattern_ind) or \
                RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, max_pattern_ind + 1):
            raise serializers.ValidationError("Wrong number of patterns")

        return lst


class VerifyTechPeopleMatchesSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 7
    verified_pairs = serializers.DictField(
        child=serializers.DictField(
            allow_empty=False,
            child=serializers.IntegerField(),
        ),
    )

    def validate_verified_pairs(self, data_dict):
        self._validate_pairs_names(data_dict)
        self._validate_pairs_data(data_dict)
        return data_dict

    def _validate_pairs_names(self, data_dict):
        for pair_name in data_dict.keys():
            if not re.fullmatch(pair_regex, pair_name):
                raise serializers.ValidationError(f"Invalid pair name: {pair_name}")

        if data_dict:
            max_pair_number = max(map(lambda s: int(s[5:]), data_dict.keys()))
            if max_pair_number > len(RedisAPIMatchesGetter.get_matching_people(self.album_pk)[0]):
                raise serializers.ValidationError(f"Wrong number of pair: {max_pair_number}")

    def _validate_pairs_data(self, data_dict):
        teach_matches = dict(zip(*RedisAPIMatchesGetter.get_matching_people(self.album_pk)))
        for pair in data_dict.values():
            if len(pair) != 1:
                raise serializers.ValidationError(f"pair must be dict with one key-value pair")

            new_per_name = next(iter(pair.keys()))
            old_per_pk = next(iter(pair.values()))

            if not re.fullmatch(person_regex, new_per_name):
                raise serializers.ValidationError(f"Invalid new person name: {new_per_name}")

            if not RedisAPIPersonDataChecker.check_person_exists(self.album_pk, int(new_per_name[7:])):
                raise serializers.ValidationError(f"person {new_per_name} does not exists")

            if teach_matches.get(old_per_pk, -1) != int(new_per_name[7:]):
                raise serializers.ValidationError(f"no such tech pair: {pair}")


class ManualMatchingPeopleSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 8
    manual_pairs = serializers.DictField(
        child=serializers.IntegerField(),
    )

    def validate_manual_pairs(self, data_dict):
        self._validate_new_ppl_names(data_dict)
        self._validate_old_ppl_pks(data_dict)
        return data_dict

    def _validate_new_ppl_names(self, data_dict):
        new_ppl_actual_indexes = tuple(next(zip(*RedisAPIMatchesGetter.get_new_unpaired_people(self.album_pk))))

        for person_name in data_dict.keys():
            if not re.fullmatch(person_regex, person_name):
                raise serializers.ValidationError(f"Invalid person name: {person_name}")

            if int(person_name[7:]) not in new_ppl_actual_indexes:
                raise serializers.ValidationError(f"{person_name} not in unpaired people")

    def _validate_old_ppl_pks(self, data_dict):
        pks = tuple(data_dict.values())

        if not len(pks) == len(set(pks)):
            raise serializers.ValidationError("multiple pairing with same old person")

        existing_old_people_pks = [person.pk for person in People.objects.filter(owner=self.context['user'])]
        not_existing_people_pks = set(pks) - set(existing_old_people_pks)
        if not_existing_people_pks:
            raise serializers.ValidationError(f"not existing old people pks: {not_existing_people_pks}")

        paired_old_people = RedisAPIMatchesGetter.get_old_paired_people(self.album_pk)
        unpaired_old_people = set(existing_old_people_pks) - set(paired_old_people)

        again_pairing_old_people = set(pks) - unpaired_old_people
        if again_pairing_old_people:
            raise serializers.ValidationError(f"trying to pair already paired: {again_pairing_old_people}")
