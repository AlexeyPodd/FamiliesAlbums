from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .auth_views import ActivateUserAPIView, PasswordResetFormView
from .routers import FavoritesRouter, PeopleRouter
from .views import MainPageAPIView, AlbumsViewSet, AnotherUserDetailAPIView, PhotoAPIView, FavoritesAlbumsViewSet, \
    FavoritesPhotosViewSet, PeopleViewSet, return_face_image_view, return_photo_with_framed_faces, \
    RecognitionAlbumsListAPIView, AlbumProcessingAPIView, SearchPersonAPIView

app_name = 'api_v1'

albums_router = SimpleRouter()
albums_router.register(r'albums', AlbumsViewSet, basename='albums')

favorites_router = FavoritesRouter()
favorites_router.register(r'albums', FavoritesAlbumsViewSet, basename='favorites_albums')
favorites_router.register(r'photos', FavoritesPhotosViewSet, basename='favorites_photos')

recognition_router = PeopleRouter()
recognition_router.register(r'people', PeopleViewSet, basename='people')


urlpatterns = [
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path('auth/users/profile/<slug:username_slug>/', AnotherUserDetailAPIView.as_view(), name='user_profile'),
    path('auth/activate/<uid>/<token>', ActivateUserAPIView.as_view(), name='activate_proxy'),
    path('auth/password/reset/<uid>/<token>', PasswordResetFormView.as_view(), name='password_reset_proxy'),
    path('main/', MainPageAPIView.as_view(), name='main'),
    path('users/<slug:username_slug>/', include(albums_router.urls)),
    path('users/<slug:username_slug>/albums/<slug:album_slug>/photos/<slug:photo_slug>/',
         PhotoAPIView.as_view(), name='photos-detail'),
    path('favorites/', include(favorites_router.urls)),
    path('recognition/', include(recognition_router.urls)),
    path('recognition/albums/', RecognitionAlbumsListAPIView.as_view(), name='recognition-albums'),
    path('recognition/processing/<slug:album_slug>/', AlbumProcessingAPIView.as_view(), name='recognition-processing'),
    path('recognition/search/', SearchPersonAPIView.as_view(), name='people-search'),
    path('face-img/', return_face_image_view, name='face-img'),
    path('photo-with-frames/', return_photo_with_framed_faces, name='photo-with-frames'),
]
