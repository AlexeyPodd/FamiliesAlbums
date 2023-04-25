from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .auth_views import ActivateUserAPIView, PasswordResetFormView
from .views import MainPageAPIView, AlbumsViewSet, AnotherUserDetailAPIView, PhotoAPIView

app_name = 'api_v1'

albums_router = SimpleRouter()
albums_router.register(r'albums', AlbumsViewSet, basename='albums')


urlpatterns = [
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path('auth/users/profile/<slug:username_slug>/', AnotherUserDetailAPIView.as_view(), name='user_profile'),
    path('auth/activate/<uid>/<token>', ActivateUserAPIView.as_view(), name='activate_proxy'),
    path('auth/password/reset/<uid>/<token>', PasswordResetFormView.as_view(), name='password_reset_proxy'),
    path('main/', MainPageAPIView.as_view(), name='main'),
    path('<slug:username_slug>/', include(albums_router.urls)),
    path('<slug:username_slug>/albums/<slug:album_slug>/photo/<slug:photo_slug>/',
         PhotoAPIView.as_view(), name='photos-detail'),
    ]
