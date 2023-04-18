from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import MainPageAPIView, UserAlbumsViewSet


app_name = 'api_v1'

router = SimpleRouter()
router.register(r'albums', UserAlbumsViewSet, basename='user_albums')

urlpatterns = [
    path('main/', MainPageAPIView.as_view(), name='main'),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path('<slug:username_slug>/', include(router.urls)),
    ]
