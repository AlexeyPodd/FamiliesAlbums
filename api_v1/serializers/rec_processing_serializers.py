from rest_framework import serializers

from .fields import DataOutputField
from .mixins import RecognitionDynamicFieldsMixin


class AlbumProcessingDataInputSerializer(RecognitionDynamicFieldsMixin, serializers.Serializer):
    start = serializers.BooleanField(write_only=True)


class AlbumProcessingSerializer(serializers.Serializer):
    stage = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    data_output = DataOutputField(read_only=True)
