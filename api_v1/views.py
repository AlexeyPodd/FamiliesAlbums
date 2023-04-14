from django.db.models import Count
from rest_framework.generics import ListAPIView
from rest_framework.viewsets import ModelViewSet

from .permissions import AlbumsPermission
from .serializers.serializers import MainPageSerializer, UserAlbumsSerializer, UserAlbumDetailSerializer
from mainapp.models import Albums


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


class UserAlbumsViewSet(ModelViewSet):
    permission_classes = (AlbumsPermission, )

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            return Albums.objects.filter(owner__username_slug=self.kwargs.get('username_slug')).annotate(
                photos_amount=Count('photos'),
            )
        else:
            return Albums.objects.filter(
                owner__username_slug=self.kwargs.get('username_slug'),
                is_private=False,
            ).annotate(
                photos_amount=Count('photos'),
            )

    def get_serializer_class(self):
        if self.detail or self.request.method == 'POST':
            return UserAlbumDetailSerializer
        else:
            return UserAlbumsSerializer
