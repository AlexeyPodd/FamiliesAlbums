from rest_framework import serializers

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
    photos_faces = serializers.DictField(child=serializers.ListField(child=serializers.IntegerField()))


class VerifyPatternsSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 4
    patterns = serializers.DictField(child=serializers.ListField(child=serializers.ListField(child=serializers.CharField())))


class GroupPatternsSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 5
    people_patterns = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))


class VerifyTechPeopleMatchesSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 7
    verified_pairs = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


class ManualMatchingPeopleSerializer(AlbumProcessingMixin, serializers.Serializer):
    stage = 8
    manual_pairs = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
