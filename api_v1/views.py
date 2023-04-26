from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Prefetch
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView, ListCreateAPIView
from rest_framework.mixins import DestroyModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from mainapp.utils import delete_from_favorites
from .permissions import AlbumsPermission, PhotosPermission
from .serializers.auth_serializers import AnotherUserSerializer
from .serializers.serializers import MainPageSerializer, AlbumsListSerializer, AlbumPostAndDetailSerializer, \
    PhotoDetailSerializer, PhotosListSerializer
from mainapp.models import Albums, Photos
from mainapp.tasks import album_deletion_task
from .utils import set_random_album_cover


class AnotherUserDetailAPIView(RetrieveAPIView):
    serializer_class = AnotherUserSerializer
    queryset = User.objects.all()
    lookup_field = 'username_slug'


class MainPageAPIView(ListAPIView):
    serializer_class = MainPageSerializer

    def get_queryset(self):
        return Albums.objects.filter(
            is_private=False,
            photos__isnull=False,
        ).annotate(
            photos_amount=Count('photos'),
        ).order_by(
            '-time_create',
        )[:16]


class AlbumsViewSet(ModelViewSet):
    permission_classes = (AlbumsPermission,)
    lookup_field = 'slug'
    lookup_url_kwarg = 'album_slug'

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            return Albums.objects.filter(owner__username_slug=self.kwargs.get('username_slug')).annotate(
                photos_amount=Count('photos'),
            ).prefetch_related(
                Prefetch('photos_set', to_attr='filtered_photos_set')
            )
        else:
            return Albums.objects.filter(
                owner__username_slug=self.kwargs.get('username_slug'),
                is_private=False,
            ).annotate(
                photos_amount=Count('photos'),
            ).prefetch_related(
                Prefetch('photos_set', queryset=Photos.objects.filter(is_private=False), to_attr='filtered_photos_set'),
            )

    def get_serializer_class(self):
        if self.detail or self.request.method == 'POST':
            return AlbumPostAndDetailSerializer
        else:
            return AlbumsListSerializer

    def perform_destroy(self, instance):
        album_deletion_task.delay(instance.pk)


class PhotoAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = (PhotosPermission,)
    serializer_class = PhotoDetailSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'photo_slug'

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            return Photos.objects.filter(album__slug=self.kwargs.get('album_slug'))
        else:
            return Photos.objects.filter(
                album__slug=self.kwargs.get('album_slug'),
                is_private=False,
            )

    def perform_destroy(self, instance):
        album = instance.album
        need_cover = album.miniature == instance
        super().perform_destroy(instance)
        if need_cover:
            set_random_album_cover(album)


class FavoritesAlbumsViewSet(ModelViewSet):
    lookup_field = 'slug'
    lookup_url_kwarg = 'album_slug'
    serializer_class = AlbumsListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Albums.objects.filter(in_users_favorites=self.request.user)

    def create(self, request, *args, **kwargs):
        album_slug = request.data.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."})

        if album.owner == request.user:
            return Response({"error": "You can add to favorites only someone else's albums."})

        if album.is_private:
            return Response({"error": "Album not found."})

        if album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "This album is already in your favorites."})

        album.in_users_favorites.add(request.user)
        album.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        album_slug = kwargs.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug, is_private=False)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."})

        if not album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "Album is not in your favorites."})

        delete_from_favorites(request.user, album)

        album.pk, album.id = None, None
        album._state.adding = True
        album.owner = request.user
        album.miniature = None
        album.save()

        for photo in Photos.objects.filter(album__slug=album_slug, is_private=False):
            photo.pk, photo.id = None, None
            photo.faces_extracted = False
            photo._state.adding = True
            photo.album = album
            photo.save()

        album.miniature = Photos.objects.get(original=Albums.objects.get(slug=album_slug).miniature.original,
                                             album=album)
        album.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        delete_from_favorites(self.request.user, instance)


class FavoritesPhotosViewSet(ModelViewSet):
    lookup_field = 'slug'
    lookup_url_kwarg = 'photo_slug'
    serializer_class = PhotosListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Photos.objects.filter(in_users_favorites=self.request.user)

    def create(self, request, *args, **kwargs):
        photo_slug = request.data.get('photo_slug')

        if photo_slug is None:
            return Response({"error": "Photo slug was not specified."})

        try:
            photo = Photos.objects.get(slug=photo_slug)
        except ObjectDoesNotExist:
            return Response({"error": "Photo not found."})

        if photo.album.owner == request.user:
            return Response({"error": "You can add to favorites only someone else's photo."})

        if photo.is_private:
            return Response({"error": "Photo not found."})

        if photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "This photo is already in your favorites."})

        photo.in_users_favorites.add(request.user)
        photo.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        photo_slug = kwargs.get('photo_slug')

        # Checking photo
        if photo_slug is None:
            return Response({"error": "Photo slug was not specified."})

        try:
            photo = Photos.objects.get(slug=photo_slug, is_private=False)
        except ObjectDoesNotExist:
            return Response({"error": "Photo not found."})

        if not photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "Photo is not in your favorites."})

        # Checking album
        album_slug = request.data.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            return Response({"error": "You don't have album with this slug."})

        if album.owner != request.user:
            return Response({"error": "You don't have album with this slug."})

        # Checking photo in album
        if Photos.objects.filter(album_id=album.pk, original=photo.original).exists():
            return Response({"error": "You already have this photo in specified album."})

        delete_from_favorites(request.user, photo)

        photo.pk, photo.id = None, None
        photo.faces_extracted = False
        photo._state.adding = True
        photo.album = album
        photo.is_private = album.is_private
        photo.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        delete_from_favorites(self.request.user, instance)
