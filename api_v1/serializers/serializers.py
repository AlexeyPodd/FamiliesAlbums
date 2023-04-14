from rest_framework import serializers
from rest_framework.reverse import reverse

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
        return reverse('api_v1_user_albums-detail',
                       kwargs={'username_slug': album.owner.username_slug, 'pk': album.pk},
                       request=self.context.get('request'))


class UserAlbumsSerializer(AlbumsMixin, serializers.ModelSerializer):
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
        return reverse('api_v1_user_albums-detail',
                       kwargs={'username_slug': album.owner.username_slug, 'pk': album.pk},
                       request=self.context.get('request'))

    def create(self, validated_data):
        instance = super().create(validated_data)
        return instance


class UserAlbumDetailSerializer(AlbumsMixin, serializers.ModelSerializer):
    miniature = MiniaturePrimaryKeyRelatedField(queryset=Photos.objects.all(),
                                                allow_null=True, write_only=True, required=False)
    download_url = serializers.SerializerMethodField()
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    miniature_url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        addition_fields = (
            'description',
            'time_create',
            'time_update',
            'miniature',
            'download_url',
            'is_private',
        )
        fields = AlbumsMixin.Meta.fields + addition_fields

    def get_download_url(self, album):
        return reverse('download', request=self.context.get('request')) + f'?album={album.slug}'

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        return instance
