from django.test import SimpleTestCase
from django.urls import reverse, resolve

from mainapp.views import MainPageView, save_album, save_photo_to_album, remove_from_favorites, add_to_favorites, \
    download, FavoritesPhotosView, FavoritesView, PhotoView, AlbumEditView, AlbumView, AlbumCreateView, UserAlbumsView, \
    AboutPageView


class TestUrls(SimpleTestCase):
    def test_main_url_is_resolves(self):
        url = reverse('main')
        self.assertEqual(resolve(url).func.view_class, MainPageView)

    def test_about_url_is_resolves(self):
        url = reverse('about')
        self.assertEqual(resolve(url).func.view_class, AboutPageView)

    def test_user_albums_url_is_resolves(self):
        url = reverse('user_albums', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, UserAlbumsView)

    def test_album_create_url_is_resolves(self):
        url = reverse('album_create', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumCreateView)

    def test_album_url_is_resolves(self):
        url = reverse('album', kwargs={'username_slug': 'some-username-slug', 'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumView)

    def test_album_edit_url_is_resolves(self):
        url = reverse('album_edit', kwargs={'username_slug': 'some-username-slug', 'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumEditView)

    def test_photo_url_is_resolves(self):
        url = reverse('photo', kwargs={'username_slug': 'some-username-slug',
                                       'album_slug': 'some-album-slug',
                                       'photo_slug': 'some-photo-slug'})
        self.assertEqual(resolve(url).func.view_class, PhotoView)

    def test_favorites_url_is_resolves(self):
        url = reverse('favorites', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, FavoritesView)

    def test_favorites_photos_url_is_resolves(self):
        url = reverse('favorites_photos', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, FavoritesPhotosView)

    def test_download_url_is_resolves(self):
        url = reverse('download')
        self.assertEqual(resolve(url).func, download)

    def test_add_to_favorites_url_is_resolves(self):
        url = reverse('add_to_favorites')
        self.assertEqual(resolve(url).func, add_to_favorites)

    def test_remove_from_favorites_url_is_resolves(self):
        url = reverse('remove_from_favorites')
        self.assertEqual(resolve(url).func, remove_from_favorites)

    def test_save_photo_to_album_url_is_resolves(self):
        url = reverse('save_photo_to_album')
        self.assertEqual(resolve(url).func, save_photo_to_album)

    def test_save_album_url_is_resolves(self):
        url = reverse('save_album')
        self.assertEqual(resolve(url).func, save_album)
