from rest_framework import serializers

from .fields import DataOutputField
from .mixins import AlbumProcessingMixin


class AlbumProcessingInfoSerializer(serializers.Serializer):
    stage = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    data_output = DataOutputField(read_only=True)


class StartAlbumProcessingSerializer(AlbumProcessingMixin, serializers.Serializer):
    start = serializers.BooleanField()
