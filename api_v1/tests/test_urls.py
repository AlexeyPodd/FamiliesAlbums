from django.test import SimpleTestCase
from django.urls import reverse, resolve

from api_v1.auth_views import ActivateUserAPIView, PasswordResetFormView
from api_v1.views import AnotherUserDetailAPIView, MainPageAPIView, PhotoAPIView, RecognitionAlbumsListAPIView, \
    AlbumProcessingAPIView, SearchPersonAPIView, return_face_image_view, return_photo_with_framed_faces, PeopleViewSet, \
    FavoritesPhotosViewSet, FavoritesAlbumsViewSet, AlbumsViewSet


class TestUrls(SimpleTestCase):
    def test_user_profile_url_resolves(self):
        url = reverse('api_v1:user_profile', kwargs={'username_slug': 'some-username'})
        self.assertEqual(resolve(url).func.view_class, AnotherUserDetailAPIView)

    def test_activate_proxy_url_resolves(self):
        url = reverse('api_v1:activate_proxy', args=['some-uid', 'some-token'])
        self.assertEqual(resolve(url).func.view_class, ActivateUserAPIView)

    def test_password_reset_proxy_url_resolves(self):
        url = reverse('api_v1:password_reset_proxy', args=['some-uid', 'some-token'])
        self.assertEqual(resolve(url).func.view_class, PasswordResetFormView)

    def test_main_url_resolves(self):
        url = reverse('api_v1:main')
        self.assertEqual(resolve(url).func.view_class, MainPageAPIView)

    def test_photos_detail_url_resolves(self):
        url = reverse('api_v1:photos-detail', kwargs={'username_slug': 'some-username',
                                                      'album_slug': 'some-album-slug',
                                                      'photo_slug': 'some-photo-slug'})
        self.assertEqual(resolve(url).func.view_class, PhotoAPIView)

    def test_recognition_albums_url_resolves(self):
        url = reverse('api_v1:recognition-albums')
        self.assertEqual(resolve(url).func.view_class, RecognitionAlbumsListAPIView)

    def test_recognition_processing_url_resolves(self):
        url = reverse('api_v1:recognition-processing', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumProcessingAPIView)

    def test_people_search_url_resolves(self):
        url = reverse('api_v1:people-search')
        self.assertEqual(resolve(url).func.view_class, SearchPersonAPIView)

    def test_face_img_url_resolves(self):
        url = reverse('api_v1:face-img')
        self.assertEqual(resolve(url).func, return_face_image_view)

    def test_photo_with_frames_url_resolves(self):
        url = reverse('api_v1:photo-with-frames')
        self.assertEqual(resolve(url).func, return_photo_with_framed_faces)

    def test_albums_list_url_resolves(self):
        url = reverse('api_v1:albums-list', kwargs={'username_slug': 'some-username'})
        self.assertEqual(resolve(url).func.cls, AlbumsViewSet)

    def test_albums_detail_url_resolves(self):
        url = reverse('api_v1:albums-detail', kwargs={'username_slug': 'some-username',
                                                      'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.cls, AlbumsViewSet)

    def test_favorites_albums_list_url_resolves(self):
        url = reverse('api_v1:favorites-albums-list')
        self.assertEqual(resolve(url).func.cls, FavoritesAlbumsViewSet)

    def test_favorites_albums_detail_url_resolves(self):
        url = reverse('api_v1:favorites-albums-detail', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.cls, FavoritesAlbumsViewSet)

    def test_favorites_photos_list_url_resolves(self):
        url = reverse('api_v1:favorites-photos-list')
        self.assertEqual(resolve(url).func.cls, FavoritesPhotosViewSet)

    def test_favorites_photos_detail_url_resolves(self):
        url = reverse('api_v1:favorites-photos-detail', kwargs={'photo_slug': 'some-photo-slug'})
        self.assertEqual(resolve(url).func.cls, FavoritesPhotosViewSet)

    def test_people_list_url_resolves(self):
        url = reverse('api_v1:people-list')
        self.assertEqual(resolve(url).func.cls, PeopleViewSet)

    def test_people_detail_url_resolves(self):
        url = reverse('api_v1:people-detail', kwargs={'person_slug': 'some-person-slug'})
        self.assertEqual(resolve(url).func.cls, PeopleViewSet)
