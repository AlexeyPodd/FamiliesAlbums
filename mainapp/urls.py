from django.urls import path
from django.views.decorators.cache import cache_page

from photoalbums.settings import TEMP_FILES_EXPIRATION_SECONDS
from .views import *

urlpatterns = [
    path('', MainPageView.as_view(), name='main'),
    path('about/', cache_page(TEMP_FILES_EXPIRATION_SECONDS)(AboutPageView.as_view()), name='about'),
    path('<slug:username_slug>/albums/', UserAlbumsView.as_view(), name='user_albums'),
    path('<slug:username_slug>/create-album/', AlbumCreateView.as_view(), name='album_create'),
    path('<slug:username_slug>/albums/<slug:album_slug>/', AlbumView.as_view(), name='album'),
    path('<slug:username_slug>/albums/<slug:album_slug>/edit/', AlbumEditView.as_view(), name='album_edit'),
    path('<slug:username_slug>/albums/<slug:album_slug>/photos/<slug:photo_slug>/', PhotoView.as_view(), name='photo'),
    path('<slug:username_slug>/favorites/', FavoritesView.as_view(), name='favorites'),
    path('<slug:username_slug>/favorites/photos/', FavoritesPhotosView.as_view(), name='favorites_photos'),
    path('download/', download, name='download'),
    path('add-to-favorites/', add_to_favorites, name='add_to_favorites'),
    path('remove-from-favorites/', remove_from_favorites, name='remove_from_favorites'),
    path('save-photo/', save_photo_to_album, name='save_photo_to_album'),
    path('save-album/', save_album, name='save_album'),
]
