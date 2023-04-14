from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import MainPageAPIView, UserAlbumsViewSet

router = DefaultRouter()
router.register(r'albums', UserAlbumsViewSet, basename='api_v1_user_albums')

urlpatterns = [
    path('main/', MainPageAPIView.as_view(), name='api_v1_main'),
    path('<slug:username_slug>/', include(router.urls)),
]
