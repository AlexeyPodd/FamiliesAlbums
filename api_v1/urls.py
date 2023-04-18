from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .auth_views import ActivateUserAPIView, PasswordResetFormView
from .views import MainPageAPIView, UserAlbumsViewSet


app_name = 'api_v1'

router = SimpleRouter()
router.register(r'albums', UserAlbumsViewSet, basename='user_albums')

urlpatterns = [
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path('auth/activate/<uid>/<token>', ActivateUserAPIView.as_view(), name='activate_proxy'),
    path('auth/password/reset/<uid>/<token>', PasswordResetFormView.as_view(), name='password_reset_proxy'),
    path('main/', MainPageAPIView.as_view(), name='main'),
    path('<slug:username_slug>/', include(router.urls)),
    ]
