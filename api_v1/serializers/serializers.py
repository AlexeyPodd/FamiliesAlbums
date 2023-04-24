from rest_framework import serializers
from rest_framework.reverse import reverse

from mainapp.utils import get_photos_title
from photoalbums.settings import ALBUM_PHOTOS_AMOUNT_LIMIT, ALBUMS_AMOUNT_LIMIT
from .mixins import AlbumsMixin
from .fields import MiniatureSlugRelatedField
from mainapp.models import Photos, Albums


class MainPageSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField()
    miniature_url = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        additional_fields = (
            'time_create',
            'photos_amount',
            'owner',
            'url',
        )
        fields = AlbumsMixin.Meta.fields + additional_fields

    def get_owner(self, album):
        return reverse('api_v1:user_profile', kwargs={'username_slug': album.owner.username_slug},
                       request=self.context.get('request'))

    def get_url(self, album):
        return reverse(
            viewname='api_v1:albums-detail',
            kwargs={'username_slug': album.owner.username_slug,
                    'album_slug': album.slug},
            request=self.context.get('request')
        )


class PhotosListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Photos
        fields = (
            'title',
            'slug',
            'date_start',
            'date_end',
            'location',
            'description',
            'time_create',
            'time_update',
            'is_private',
            'original',
        )
        extra_kwargs = {
            'original': {'read_only': True},
        }


class AlbumsListSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField(read_only=True)
    miniature_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        addition_fields = (
            'photos_amount',
            'is_private',
            'url',
        )
        fields = AlbumsMixin.Meta.fields + addition_fields

    def get_url(self, album):
        return reverse(
            viewname='api_v1:albums-detail',
            kwargs={'username_slug': album.owner.username_slug,
                    'album_slug': album.slug},
            request=self.context.get('request')
        )


class AlbumPostAndDetailSerializer(AlbumsMixin, serializers.ModelSerializer):
    miniature = MiniatureSlugRelatedField(queryset=Photos.objects.all(), slug_field='slug',
                                          allow_null=True, write_only=True, required=False)
    download_url = serializers.SerializerMethodField()
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    miniature_url = serializers.SerializerMethodField()
    photos = PhotosListSerializer(many=True, read_only=True, source='filtered_photos_set')
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
            'owner',
        )
        fields = AlbumsMixin.Meta.fields + addition_fields

    def get_download_url(self, album):
        return reverse('download', request=self.context.get('request')) + f'?album={album.slug}'

    def create(self, validated_data):
        self.validate_albums_amount(owner=validated_data["owner"])
        uploaded_images = self._pop_uploaded_images(validated_data)
        instance = super().create(validated_data)
        self._create_new_photos(instance, uploaded_images)
        self._set_random_cover(instance)
        return instance

    def update(self, instance, validated_data):
        uploaded_images = self._pop_uploaded_images(validated_data)
        instance = super().update(instance, validated_data)

        # Adding uploaded photos to album and choosing random cover
        had_photos = self.instance.photos_set.exists()
        self._create_new_photos(instance, uploaded_images)
        if not had_photos:
            self._set_random_cover(instance)

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

    def validate_uploaded_photos(self, value):
        instance = getattr(self, 'instance', None)
        stored_photos_amount = 0 if instance is None else instance.photos_set.count()
        if len(value) + stored_photos_amount > ALBUM_PHOTOS_AMOUNT_LIMIT:
            message = f"You can upload only {ALBUM_PHOTOS_AMOUNT_LIMIT} photos in each album"
            raise serializers.ValidationError(message)
        return value

    def validate_albums_amount(self, owner):
        if self.Meta.model.objects.filter(owner=owner).count() >= ALBUMS_AMOUNT_LIMIT:
            message = f"You can create only {ALBUM_PHOTOS_AMOUNT_LIMIT} albums"
            raise serializers.ValidationError(message)

    @staticmethod
    def _set_random_cover(album):
        cover = album.photos_set.filter(is_private=False).order_by('?').first()
        if cover:
            album.miniature = cover
            album.save()

    def validate_title(self, title):
        """Checking is title uniq for this user"""

        instance = getattr(self, 'instance')
        user = self.context['request'].user
        namesake_album_queryset = Albums.objects.filter(owner_id=user.pk, title=title)
        if namesake_album_queryset.exists() and namesake_album_queryset[0] != instance:
            message = 'You already have album with this title. Please, choose another title for this one.'
            raise serializers.ValidationError(message)

        return title

    def validate_date_start(self, value):
        instance = getattr(self, 'instance')
        if instance is not None:
            earliest_photo_date = instance.photos_set.order_by('date_start').first().date_start
            if instance.date_start and instance.date_start > earliest_photo_date:
                message = 'There is a photo with an earlier date.'
                raise serializers.ValidationError(message)
        return value

    def validate_date_end(self, value):
        instance = getattr(self, 'instance')
        if instance is not None:
            latest_photo_date = instance.photos_set.order_by('-date_end').first().date_end
            if instance.date_end and instance.date_end < latest_photo_date:
                message = 'There is a photo with an later date.'
                raise serializers.ValidationError(message)
        return value
