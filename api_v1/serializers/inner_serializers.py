from rest_framework import serializers
from rest_framework.reverse import reverse

from recognition.models import Patterns, Faces


class FaceSerializer(serializers.ModelSerializer):
    face_img_url = serializers.SerializerMethodField()
    album_url = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Faces
        fields = ('face_img_url', 'album_url', 'photo_url')

    def get_photo_url(self, face):
        return reverse(
            viewname='api_v1:photos-detail',
            request=self.context['request'],
            kwargs={
                'username_slug': face.photo.album.owner.username_slug,
                'album_slug': face.photo.album.slug,
                'photo_slug': face.photo.slug,
            }
        )

    def get_face_img_url(self, face):
        return reverse('api_v1:face-img', request=self.context['request']) + f"face={face.slug}"

    def get_album_url(self, face):
        return reverse(
            viewname='api_v1:albums-detail',
            request=self.context['request'],
            kwargs={
                'username_slug': face.photo.album.owner.username_slug,
                'album_slug': face.photo.album.slug,
            }
        )


class PatternsSerializer(serializers.ModelSerializer):
    faces = FaceSerializer(many=True, read_only=True, source='faces_set')

    class Meta:
        model = Patterns
        fields = ('faces',)
