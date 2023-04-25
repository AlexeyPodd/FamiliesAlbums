from django.db.models import Count, Prefetch
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from .permissions import AlbumsPermission, PhotosPermission
from .serializers.auth_serializers import AnotherUserSerializer
from .serializers.serializers import MainPageSerializer, AlbumsListSerializer, AlbumPostAndDetailSerializer, \
    PhotoDetailSerializer
from mainapp.models import Albums, Photos
from mainapp.tasks import album_deletion_task
from .utils import set_random_album_cover


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


class AnotherUserDetailAPIView(RetrieveAPIView):
    serializer_class = AnotherUserSerializer
    queryset = User.objects.all()
    lookup_field = 'username_slug'
