from django.urls import path

from .views import *

urlpatterns = [
    path('', MainPageView.as_view(), name='main'),
    path('about', AboutPageView.as_view(), name='about'),
    path('<slug:username_slug>/albums/', UserAlbumsView.as_view(), name='user_albums'),
    path('<slug:username_slug>/create_album/', AlbumCreateView.as_view(), name='album_create'),
    path('<slug:username_slug>/albums/<slug:album_slug>/', AlbumView.as_view(), name='album'),
    path('<slug:username_slug>/albums/<slug:album_slug>/edit/', AlbumEditView.as_view(), name='album_edit'),
    path('<slug:username_slug>/albums/<slug:album_slug>/photos/<slug:photo_slug>/', PhotoView.as_view(), name='photo'),
    path('download/', download, name='download'),
    path('<slug:username_slug>/favorites/', FavoritesView.as_view(), name='favorites'),
    path('<slug:username_slug>/favorites/photos/', FavoritesPhotosView.as_view(), name='favorites_photos'),
    path('add_to_favorites/', add_to_favorites, name='add_to_favorites'),
    path('save_photo/', save_photo_to_album, name='save_photo_to_album'),
    path('remove_from_favorites/', remove_from_favorites, name='remove_from_favorites'),
    path('save_album/', save_album, name='save_album'),
]
