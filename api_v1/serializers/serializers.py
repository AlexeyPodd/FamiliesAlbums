from rest_framework import serializers
from rest_framework.reverse import reverse

from mainapp.utils import get_photos_title
from photoalbums.settings import ALBUM_PHOTOS_AMOUNT_LIMIT, ALBUMS_AMOUNT_LIMIT
from recognition.models import People
from .inner_serializers import PatternsSerializer
from .mixins import AlbumsMixin, AlbumMiniatureMixin
from .fields import MiniatureSlugRelatedField
from mainapp.models import Photos, Albums
from ..utils import set_random_album_cover, clear_photo_favorites_and_faces


class MainPageSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField()
    miniature_url = serializers.SerializerMethodField()
    owner_profile = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta(AlbumsMixin.Meta):
        additional_fields = (
            'time_create',
            'photos_amount',
            'url',
        )
        fields = AlbumsMixin.Meta.fields + additional_fields

    def get_url(self, album):
        return reverse(
            viewname='api_v1:albums-detail',
            kwargs={'username_slug': album.owner.username_slug,
                    'album_slug': album.slug},
            request=self.context.get('request')
        )


class PhotoDetailSerializer(serializers.ModelSerializer):
    owner_profile = serializers.SerializerMethodField()

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
            'owner_profile',
        )
        extra_kwargs = {'original': {'read_only': True}}

    def get_owner_profile(self, photo):
        if self.context['request'].user == photo.album.owner:
            return self.context['request'].build_absolute_uri('/api/v1/auth/users/me/')
        else:
            return self.context['request'].build_absolute_uri(
                f'/api/v1/auth/users/profile/{photo.album.owner.username_slug}/',
            )

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        # If photo became private
        if validated_data.get('is_private', False):
            clear_photo_favorites_and_faces(instance)

            # Changing cover of album while it's became private
            if instance.album.miniature == instance and not instance.album.is_private:
                set_random_album_cover(album=instance.album)

        return instance

    def validate_date_start(self, value):
        instance = getattr(self, 'instance')
        album_date_start = instance.album.date_start
        if album_date_start and value < album_date_start:
            message = 'This date does not match the album date period.'
            raise serializers.ValidationError(message)
        return value

    def validate_date_end(self, value):
        instance = getattr(self, 'instance')
        album_date_end = instance.album.date_end
        if album_date_end and value > album_date_end:
            message = 'This date does not match the album date period.'
            raise serializers.ValidationError(message)
        return value

    def validate_is_private(self, privacy):
        instance = getattr(self, 'instance')
        if instance.album.is_private and not privacy:
            message = 'In private album can not be any public photos.'
            raise serializers.ValidationError(message)
        return privacy

    def validate(self, data):
        date_start = data.get('date_start')
        date_end = data.get('date_end')
        if date_start and date_end and date_start > date_end:
            message = "The end of the photo period can't be earlier than the beginning"
            raise serializers.ValidationError(message)
        return super().validate(data)


class PhotosListSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Photos
        fields = (
            'title',
            'date_start',
            'date_end',
            'location',
            'is_private',
            'original',
            'url',
        )
        extra_kwargs = {'original': {'read_only': True}}

    def get_url(self, photo):
        return reverse(
            viewname='api_v1:photos-detail',
            kwargs={'username_slug': photo.album.owner.username_slug,
                    'album_slug': photo.album.slug,
                    'photo_slug': photo.slug},
            request=self.context.get('request')
        )


class AlbumsListSerializer(AlbumsMixin, serializers.ModelSerializer):
    photos_amount = serializers.IntegerField(read_only=True)
    miniature_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    owner_profile = serializers.SerializerMethodField()

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
    owner_profile = serializers.SerializerMethodField()
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
        set_random_album_cover(instance)
        return instance

    def update(self, instance, validated_data):
        uploaded_images = self._pop_uploaded_images(validated_data)
        instance = super().update(instance, validated_data)

        # Adding uploaded photos to album and choosing random cover
        had_photos = self.instance.photos_set.exists()
        self._create_new_photos(instance, uploaded_images)
        if not had_photos:
            set_random_album_cover(instance)

        # Changing privacy of album
        if validated_data.get('is_private') is not None:
            self._change_album_privacy(instance)

        return instance

    def validate(self, data):
        date_start = data.get('date_start')
        date_end = data.get('date_end')
        if date_start and date_end and date_start > date_end:
            message = "The end of the album period can't be earlier than the beginning"
            raise serializers.ValidationError(message)
        return super().validate(data)

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
            earliest_photo = instance.photos_set.exclude(date_start=None).order_by('date_start').first()
            if earliest_photo and value > earliest_photo.date_start:
                message = 'There is a photo with an earlier date.'
                raise serializers.ValidationError(message)
        return value

    def validate_date_end(self, value):
        instance = getattr(self, 'instance')
        if instance is not None:
            latest_photo = instance.photos_set.exclude(date_end=None).order_by('-date_end').first()
            if latest_photo and value < latest_photo.date_end:
                message = 'There is a photo with an later date.'
                raise serializers.ValidationError(message)
        return value

    @staticmethod
    def _change_album_privacy(album):
        for photo in album.photos_set.all():
            photo.is_private = album.is_private
            if album.is_private:
                clear_photo_favorites_and_faces(photo, commit=False)
            photo.save()

        if album.is_private:
            album.in_users_favorites.clear()

        album.save()


class PeopleListSerializer(serializers.HyperlinkedModelSerializer):
    picture_url = serializers.SerializerMethodField()

    class Meta:
        model = People
        fields = ('name', 'picture_url', 'url')
        extra_kwargs = {
            'url': {'view_name': 'api_v1:people-detail', 'lookup_field': 'slug', 'lookup_url_kwarg': 'person_slug'}
        }

    def get_picture_url(self, person):
        return reverse('api_v1:face-img', request=self.context.get('request'))\
            + f"?face={person.patterns_set.first().faces_set.first().slug}"


class PersonSerializer(serializers.ModelSerializer):
    patterns = PatternsSerializer(many=True, read_only=True, source='patterns_set')
    patterns_amount = serializers.IntegerField(read_only=True)
    photos_amount = serializers.IntegerField(read_only=True)
    albums_amount = serializers.IntegerField(read_only=True)
    search_url = serializers.SerializerMethodField()

    class Meta:
        model = People
        fields = (
            'name',
            'slug',
            'patterns_amount',
            'photos_amount',
            'albums_amount',
            'search_url',
            'patterns',
        )

    def get_search_url(self, person):
        return reverse('api_v1:people-search', request=self.context['request']) + f"?person={person.slug}"


class RecognitionAlbumsSerializer(AlbumMiniatureMixin, serializers.ModelSerializer):
    processed_photos_amount = serializers.IntegerField(read_only=True)
    public_photos_amount = serializers.IntegerField(read_only=True)
    miniature_url = serializers.SerializerMethodField()
    processing_url = serializers.SerializerMethodField()

    class Meta:
        model = Albums
        fields = (
            'title',
            'miniature_url',
            'processed_photos_amount',
            'public_photos_amount',
            'processing_url',
        )

    def get_processing_url(self, album):
        return reverse('api_v1:recognition-processing', request=self.context['request'],
                       kwargs={'album_slug': album.slug})


class FoundedPeopleSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='api_v1:people-detail', lookup_field='slug',
                                               lookup_url_kwarg='person_slug')
    face_image = serializers.SerializerMethodField()
    patterns_images = serializers.SerializerMethodField()
    photos_amount = serializers.IntegerField()
    albums_amount = serializers.IntegerField()

    class Meta:
        model = People
        fields = (
            'name',
            'url',
            'face_image',
            'patterns_images',
            'photos_amount',
            'albums_amount',
        )

    def get_face_image(self, person):
        return reverse('api_v1:face-img', request=self.context['request']) + \
            f'?face={person.patterns_set.first().faces_set.first().slug}'

    def get_patterns_images(self, person):
        patterns = person.patterns_set.all()[1:5]
        image_urls = list(map(lambda p: reverse('api_v1:face-img',
                                                request=self.context['request']) + p.faces_set.first().slug, patterns))
        return image_urls


class SearchStartOverSerializer(serializers.Serializer):
    start = serializers.BooleanField()

    def validate_start(self, value):
        if not value:
            raise serializers.ValidationError("start parameter must be set True.")
        return value
