from rest_framework import serializers
from rest_framework.reverse import reverse

from mainapp.utils import get_photos_title
from .mixins import AlbumsMixin
from .fields import MiniaturePrimaryKeyRelatedField
from mainapp.models import Photos


class MainPageSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField()
    miniature_url = serializers.SerializerMethodField()
    album_detail_url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        additional_fields = (
            'time_create',
            'photos_amount',
            'album_detail_url',
        )
        fields = AlbumsMixin.Meta.fields + additional_fields

    def get_album_detail_url(self, album):
        return reverse('api_v1:user_albums-detail',
                       kwargs={'username_slug': album.owner.username_slug, 'pk': album.pk},
                       request=self.context.get('request'))


class UserAlbumsListSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField(read_only=True)
    album_detail_url = serializers.SerializerMethodField()
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    miniature_url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        addition_fields = (
            'photos_amount',
            'album_detail_url',
            'is_private',
        )
        fields = AlbumsMixin.Meta.fields + addition_fields

    def get_album_detail_url(self, album):
        return reverse('api_v1:user_albums-detail',
                       kwargs={'username_slug': album.owner.username_slug, 'pk': album.pk},
                       request=self.context.get('request'))


class PhotosSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Photos
        fields = (
            'title',
            'date_start',
            'date_end',
            'location',
            'is_private',
            'image_url',
        )

    def get_image_url(self, photo):
        image_url = photo.original.url
        request = self.context.get('request')
        return request.build_absolute_uri(image_url)


class UserAlbumPostAndDetailSerializer(AlbumsMixin, serializers.ModelSerializer):
    miniature = MiniaturePrimaryKeyRelatedField(queryset=Photos.objects.all(),
                                                allow_null=True, write_only=True, required=False)
    download_url = serializers.SerializerMethodField()
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    miniature_url = serializers.SerializerMethodField()
    photos = PhotosSerializer(many=True, read_only=True, source='photos_set')
    uploaded_photos = serializers.ListField(
        child=serializers.ImageField(use_url=False),
        write_only=True, required=False,
    )

    class Meta(AlbumsMixin.Meta):
        addition_fields = (
            'description',
            'time_create',
            'time_update',
            'miniature',
            'download_url',
            'is_private',
            'photos',
            'uploaded_photos',
        )
        fields = AlbumsMixin.Meta.fields + addition_fields

    def get_download_url(self, album):
        return reverse('download', request=self.context.get('request')) + f'?album={album.slug}'

    def create(self, validated_data):
        uploaded_images = self._pop_uploaded_images(validated_data)
        instance = super().create(validated_data)
        self._create_new_photos(instance, uploaded_images)
        return instance

    def update(self, instance, validated_data):
        uploaded_images = self._pop_uploaded_images(validated_data)
        instance = super().update(instance, validated_data)
        self._create_new_photos(instance, uploaded_images)
        return instance

    @staticmethod
    def _pop_uploaded_images(validated_data):
        try:
            return validated_data.pop('uploaded_photos')
        except KeyError:
            return

    @staticmethod
    def _create_new_photos(instance, uploaded_images):
        if uploaded_images is not None:
            for image in uploaded_images:
                Photos.objects.create(
                    title=get_photos_title(image.name),
                    date_start=instance.date_start,
                    date_end=instance.date_end,
                    location=instance.location,
                    is_private=instance.is_private,
                    album=instance,
                    original=image,
                )
