import re

from rest_framework import serializers

from mainapp.models import Photos
from recognition.redis_interface.functional_api import RedisAPIPhotoSlug, RedisAPIPhotoDataGetter, \
    RedisAPIPatternDataGetter, RedisAPIPatternDataChecker
from .fields import DataOutputField
from .mixins import AlbumProcessingMixin


# Serializer for GET requests
class AlbumProcessingInfoSerializer(serializers.Serializer):
    stage = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    data_output = DataOutputField(read_only=True)


# Serializers below are for POST requests
# ----------------------------------------------------------------------------------------------------------------------
class StartAlbumProcessingSerializer(AlbumProcessingMixin, serializers.Serializer):
    start = serializers.BooleanField()

    def validate_start(self, value):
        if not value:
            raise serializers.ValidationError("start parameter must be set True.")
        return value

    def validate(self, attrs):
        if self.status == 'processing':
            raise serializers.ValidationError('Processing should be completed before starting over.')
        return attrs


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
            raise serializers.ValidationError("Invalid photos slugs")

    @staticmethod
    def _validate_face_numbers(data_dict):
        photo_slugs = tuple(data_dict.keys())
        photos = Photos.objects.filter(slug__in=photo_slugs)
        for photo in photos:
            face_numbers = data_dict[photo.slug]
            if any(map(lambda x: x < 1 or x > RedisAPIPhotoDataGetter.get_faces_amount_in_photo(photo.pk),
                       face_numbers)):
                raise serializers.ValidationError("Invalid face numbers")

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
        regex = re.compile(r'pattern_[1-9][0-9]*')
        if not all(map(lambda s: re.fullmatch(regex, s), data_dict.keys())):
            raise serializers.ValidationError("Invalid patterns names")

        if not all(map(lambda s: RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, int(s[8:])),
                       data_dict.keys())):
            raise serializers.ValidationError("Pattern does not exist or invalid")

        if RedisAPIPatternDataGetter.get_pattern_faces_amount(self.album_pk, len(data_dict) + 1):
            raise serializers.ValidationError("Not all patterns data received")

    def _validate_faces_names(self, data_dict):
        regex = re.compile(r'face_[1-9][0-9]*')
        for pattern_name, separated_faces_list in data_dict.items():
            faces_names = [face_name for lst in separated_faces_list for face_name in lst]
            if not all(map(lambda f: re.fullmatch(regex, f), faces_names)):
                raise serializers.ValidationError("Invalid faces names")

            # Validating uniqueness and correct numbering
            max_face_number = max(map(lambda s: int(s[5:]), faces_names))
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
        regex = re.compile(r'pattern_[1-9][0-9]*')
        pattern_list = [pattern for group in lst for pattern in group]
        if not all(map(lambda p: re.fullmatch(regex, p), pattern_list)):
            raise serializers.ValidationError("Invalid pattern names")

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
        allow_empty=False,
        child=serializers.ListField(
            allow_empty=False,
            child=serializers.CharField(),
        ),
    )

    def validate_verified_pairs(self, data_dict):
        self._validate_pairs_naming(data_dict)
        self._validate_pairs_data(data_dict)
        return data_dict


class ManualMatchingPeopleSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 8
    manual_pairs = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
