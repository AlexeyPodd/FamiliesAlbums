from django.urls import path, include, re_path
from rest_framework.routers import SimpleRouter

from .auth_views import ActivateUserAPIView, PasswordResetFormView
from .views import MainPageAPIView, AlbumsViewSet, AnotherUserDetailAPIView, PhotosViewSet

app_name = 'api_v1'

albums_router = SimpleRouter()
albums_router.register(r'albums', AlbumsViewSet, basename='albums')

photos_router = SimpleRouter()
photos_router.register(r'(?P<username_slug>[^/.]+)/photos', PhotosViewSet, basename='photos')


urlpatterns = [
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path('auth/users/profile/<slug:username_slug>/', AnotherUserDetailAPIView.as_view(), name='user_profile'),
    path('auth/activate/<uid>/<token>', ActivateUserAPIView.as_view(), name='activate_proxy'),
    path('auth/password/reset/<uid>/<token>', PasswordResetFormView.as_view(), name='password_reset_proxy'),
    path('main/', MainPageAPIView.as_view(), name='main'),
    path('<slug:username_slug>/', include(albums_router.urls)),
    re_path('', include(photos_router.urls)),
    ]
