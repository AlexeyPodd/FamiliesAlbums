import base64
import io
import re
import zipfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils.datetime_safe import datetime

from accounts.models import User
from mainapp.models import Albums, Photos
from photoalbums.settings import ALBUMS_AMOUNT_LIMIT, ALBUM_PHOTOS_AMOUNT_LIMIT


class TestView(TestCase):
    dummy_username = 'test_user'
    dummy_password = '12345'
    dummy_email = 'test@mail.com'
    dummy_2_username = 'test_user_2'
    dummy_2_password = '67890'
    dummy_2_email = 'test2@mail.com'
    dummy_album_title = 'test_album'
    dummy_photo_title = 'test_photo'

    viewname = 'main'
    full_kwargs = {
        'username_slug': dummy_username,
        'album_slug': dummy_username + '-' + dummy_album_title,
        'photo_slug': dummy_photo_title,
    }
    url_variables = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cache.clear()



        url_kwargs = {key: cls.full_kwargs.get(key) for key in cls.url_variables}
        cls.url = reverse(viewname=cls.viewname, kwargs=url_kwargs)

    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username=self.dummy_username,
            password=self.dummy_password,
            email=self.dummy_email,
        )
        self.second_user = User.objects.create_user(
            username=self.dummy_2_username,
            password=self.dummy_2_password,
            email=self.dummy_2_email,
        )

        if 'album_slug' in self.url_variables and 'username_slug' in self.url_variables:
            test_image = SimpleUploadedFile(
                f"{self.dummy_photo_title}.jpeg",
                base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                                 "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                                 "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
            self.album = Albums.objects.create(title=self.dummy_album_title, owner=self.user)
            self.photo = Photos.objects.create(title=self.dummy_photo_title, album=self.album, original=test_image)
            self.private_photo = Photos.objects.create(title=self.dummy_photo_title, album=self.album,
                                                       is_private=True, original=test_image)


class TestManagementView(TestView):
    def setUp(self):
        super().setUp()
        test_image = SimpleUploadedFile(
            f"{self.dummy_photo_title}.jpg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
        self.album = Albums.objects.create(title=self.dummy_album_title, owner=self.user)
        self.photo = Photos.objects.create(title=self.dummy_photo_title, album=self.album, original=test_image)
        self.private_photo = Photos.objects.create(title=self.dummy_photo_title, album=self.album,
                                                   is_private=True, original=test_image)


class TestMainPageView(TestView):
    viewname = 'main'

    def test_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/index.html')


class TestAboutPageView(TestView):
    viewname = 'about'

    def test_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/about.html')


class TestUserAlbumsView(TestView):
    viewname = 'user_albums'
    url_variables = ['username_slug']

    def test_not_authorised_with_no_albums_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_not_authorised_with_private_album_GET(self):
        Albums.objects.create(title='test_private', is_private=True, owner=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_not_authorised_with_public_album_GET(self):
        Albums.objects.create(title='test_public', owner=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/albums.html')

    def test_authorised_GET(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/albums.html')


class TestAlbumCreateView(TestView):
    viewname = 'album_create'
    url_variables = ['username_slug']

    def test_not_authorised_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_not_owner_GET(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_owner_GET(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_albums_limit_reached_GET(self):
        for i in range(ALBUMS_AMOUNT_LIMIT):
            Albums.objects.create(title=f'test_album_{i}', owner=self.user)
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_POST_creates_new_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        creating_album_title = 'test_creating'

        response = self.client.post(self.url, {'title': creating_album_title})

        self.assertRedirects(
            response,
            reverse('album_edit', kwargs={'username_slug': self.user.username_slug,
                                          'album_slug': f"{self.user.username_slug}-{creating_album_title}"}),
        )
        self.assertEqual(self.user.albums.first().title, creating_album_title)

    def test_POST_no_data(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.albums.count(), 0)

    def test_POST_riches_photos_amount_limit(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        creating_album_title = 'test_creating'
        photo_files = [SimpleUploadedFile(
            f"{i}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
                       for i in range(ALBUM_PHOTOS_AMOUNT_LIMIT + 1)]

        response = self.client.post(self.url, {'title': creating_album_title, 'images': photo_files})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.albums.count(), 0)

    def test_POST_uploaded_photos_created(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        creating_album_title = 'test_creating'
        photo_files = [SimpleUploadedFile(
            f"{i}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
                       for i in range(ALBUM_PHOTOS_AMOUNT_LIMIT)]

        response = self.client.post(self.url, {'title': creating_album_title, 'images': photo_files})

        self.assertEqual(response.status_code, 302)
        photos = self.user.albums.first().photos_set.all()
        self.assertEqual(photos.count(), ALBUM_PHOTOS_AMOUNT_LIMIT)

    def test_POST_cover_set(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        creating_album_title = 'test_creating'
        photo_files = [SimpleUploadedFile(
            f"{i}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
                       for i in range(ALBUM_PHOTOS_AMOUNT_LIMIT)]

        self.client.post(self.url, {'title': creating_album_title, 'images': photo_files})

        self.assertIsNotNone(self.user.albums.first().miniature)


class TestAlbumView(TestView):
    viewname = 'album'
    url_variables = ['username_slug', 'album_slug']

    def test_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/album_photos.html')

    def test_GET_private_album_visible_for_owner_only(self):
        self.album.is_private = True
        self.album.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

        self.client.login(username=self.dummy_username, password=self.dummy_password)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_GET_private_photos_visible_for_owner_only(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["object_list"]), 1)

        self.client.login(username=self.dummy_username, password=self.dummy_password)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["object_list"]), 2)


class TestAlbumEditView(TestView):
    viewname = 'album_edit'
    url_variables = ['username_slug', 'album_slug']

    def test_GET_by_owner(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/album_edit.html')

    def test_GET_by_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_by_not_owner(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            reverse('album', kwargs={'username_slug': self.user.username_slug,
                                     'album_slug': self.album.slug}),
        )

    def test_POST_edit_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        new_album_title = self.album.title + '777'
        data = {
            'title': new_album_title,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(
            response,
            reverse('album', kwargs={'username_slug': self.user.username_slug,
                                     'album_slug': self.album.slug}),
        )
        self.album.refresh_from_db()
        self.assertEqual(self.album.title, new_album_title)

    def test_POST_photo_deletion(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        data = {
            'title': self.album.title,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
            'photos_set-1-DELETE': True,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(
            response,
            reverse('album', kwargs={'username_slug': self.user.username_slug,
                                     'album_slug': self.album.slug}),
        )
        self.album.refresh_from_db()
        self.assertEqual(self.album.photos_set.count(), 1)

    def test_POST_uploaded_photos_created(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        photo_files = [SimpleUploadedFile(
            f"{i}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
                       for i in range(ALBUM_PHOTOS_AMOUNT_LIMIT - 2)]

        data = {
            'title': self.album.title,
            'images': photo_files,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(response, self.url)
        self.album.refresh_from_db()
        self.assertEqual(self.album.photos_set.count(), ALBUM_PHOTOS_AMOUNT_LIMIT)

    def test_POST_uploaded_photos_limit_reached(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        photo_files = [SimpleUploadedFile(
            f"{i}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
                        for i in range(ALBUM_PHOTOS_AMOUNT_LIMIT)]

        data = {
            'title': self.album.title,
            'images': photo_files,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
        }
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.album.refresh_from_db()
        self.assertEqual(self.album.photos_set.count(), 2)

    def test_POST_photos_dates_earlier_than_album(self):
        test_image = SimpleUploadedFile(
            f"{self.dummy_photo_title}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        earlier_photo = Photos.objects.create(
            title='earlier_photo',
            date_start=datetime.strptime('17/07/2018', '%d/%m/%Y'),
            album_id=self.album.pk,
            original=test_image,
        )

        data = {
            'title': self.album.title,
            'date_start_day': 1,
            'date_start_month': 1,
            'date_start_year': 2019,
            'photos_set-TOTAL_FORMS': 3,
            'photos_set-INITIAL_FORMS': 3,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
            'photos_set-2-id': earlier_photo.pk,
            'photos_set-2-title': earlier_photo.title,
            'photos_set-2-date_start_day': 17,
            'photos_set-2-date_start_month': 7,
            'photos_set-2-date_start_year': 2018,
        }
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)

    def test_POST_photos_dates_later_than_album(self):
        test_image = SimpleUploadedFile(
            f"{self.dummy_photo_title}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        later_photo = Photos.objects.create(
            title='later_photo',
            date_end=datetime.strptime('17/07/2018', '%d/%m/%Y'),
            album_id=self.album.pk,
            original=test_image,
        )

        data = {
            'title': self.album.title,
            'date_end_day': 1,
            'date_end_month': 1,
            'date_end_year': 2015,
            'photos_set-TOTAL_FORMS': 3,
            'photos_set-INITIAL_FORMS': 3,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': self.private_photo.is_private,
            'photos_set-2-id': later_photo.pk,
            'photos_set-2-title': later_photo.title,
            'photos_set-2-date_end_day': 17,
            'photos_set-2-date_end_month': 7,
            'photos_set-2-date_end_year': 2018,
        }
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)

    def test_POST_set_cover_for_empty_album_when_upload_photos(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        self.photo.delete()
        self.private_photo.delete()
        image = SimpleUploadedFile(
            f"{self.dummy_photo_title}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")

        data = {
            'title': self.album.title,
            'images': [image],
            'photos_set-TOTAL_FORMS': 0,
            'photos_set-INITIAL_FORMS': 0,
        }
        response = self.client.post(self.url, data)

        self.album.refresh_from_db()
        self.assertRedirects(response, self.url)
        self.assertIsNotNone(self.album.miniature)
        self.assertEqual(self.album.miniature.title, self.dummy_photo_title)

    def test_POST_set_new_cover_when_deleting_old(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        self.album.miniature = self.photo
        self.private_photo.is_private = False
        self.album.save()
        self.private_photo.save()

        data = {
            'title': self.album.title,
            'miniature': self.album.miniature.pk,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-0-DELETE': True,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(
            response,
            reverse('album', kwargs={'username_slug': self.user.username_slug,
                                     'album_slug': self.album.slug}),
        )
        self.album.refresh_from_db()
        self.assertFalse(Photos.objects.filter(pk=self.photo.pk).exists())
        self.assertIsNotNone(self.album.miniature)
        self.assertEqual(self.album.miniature, self.private_photo)

    def test_POST_set_new_cover_when_old_become_private(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        self.private_photo.is_private = False
        self.private_photo.save()
        self.album.miniature = self.private_photo
        self.album.save()

        data = {
            'title': self.album.title,
            'miniature': self.album.miniature.pk,
            'photos_set-TOTAL_FORMS': 2,
            'photos_set-INITIAL_FORMS': 2,
            'photos_set-0-id': self.photo.pk,
            'photos_set-0-title': self.photo.title,
            'photos_set-1-id': self.private_photo.pk,
            'photos_set-1-title': self.private_photo.title,
            'photos_set-1-is_private': True,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(
            response,
            reverse('album', kwargs={'username_slug': self.user.username_slug,
                                     'album_slug': self.album.slug}),
        )
        self.private_photo.refresh_from_db()
        self.album.refresh_from_db()
        self.assertTrue(self.private_photo.is_private)
        self.assertIsNotNone(self.album.miniature)
        self.assertEqual(self.album.miniature, self.photo)


class TestPhotoView(TestView):
    viewname = 'photo'
    url_variables = ['username_slug', 'album_slug', 'photo_slug']

    def test_GET(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/photo.html')

    def test_GET_private_album_visible_for_owner_only(self):
        self.photo.is_private = True
        self.photo.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

        self.client.login(username=self.dummy_username, password=self.dummy_password)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_GET_incorrect_album_slug(self):
        url_kwargs = self.full_kwargs.copy()
        url_kwargs['album_slug'] = 'incorrect_album_slug'
        url = reverse(self.viewname, kwargs=url_kwargs)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_GET_owner_have_link_to_next_private_photo(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        next_photo_url = reverse(self.viewname, kwargs={'username_slug': self.dummy_username,
                                                        'album_slug': self.album.slug,
                                                        'photo_slug': self.private_photo.slug})
        self.assertEqual(response.context['next_photo_url'], next_photo_url)

    def test_GET_not_owner_do_not_have_link_to_next_private_photo(self):
        response = self.client.get(self.url)

        self.assertIsNone(response.context['next_photo_url'])


class TestFavoritesView(TestView):
    viewname = 'favorites'
    url_variables = ['username_slug']

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_authorised_not_owner(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        url = reverse(self.viewname, kwargs={'username_slug': self.dummy_2_username})

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse(self.viewname, kwargs={'username_slug': self.dummy_username}),
        )

    def test_GET_authorised_owner(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/favorites.html')

    def test_GET_queryset_is_correct(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title=self.dummy_album_title, owner=self.user)
        album.in_users_favorites.add(self.second_user)
        album.save()
        url = reverse(self.viewname, kwargs={'username_slug': self.dummy_2_username})

        response = self.client.get(url)

        self.assertEqual(len(response.context['albums']), 1)
        self.assertIn(album, response.context['albums'])


class TestFavoritesPhotosView(TestView):
    viewname = 'favorites_photos'
    url_variables = ['username_slug']

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_authorised_not_owner(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        url = reverse(self.viewname, kwargs={'username_slug': self.dummy_2_username})

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse(self.viewname, kwargs={'username_slug': self.dummy_username}),
        )

    def test_GET_authorised_owner(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'mainapp/favorites_photos.html')

    def test_GET_queryset_is_correct(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title=self.dummy_album_title, owner=self.user)
        test_image = SimpleUploadedFile(
            f"{self.dummy_photo_title}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")
        photo = Photos.objects.create(title=self.dummy_photo_title, album=album, original=test_image)
        photo.in_users_favorites.add(self.second_user)
        photo.save()
        url = reverse(self.viewname, kwargs={'username_slug': self.dummy_2_username})

        response = self.client.get(url)

        self.assertEqual(len(response.context['photos']), 1)
        self.assertIn(photo, response.context['photos'])


class TestDownload(TestManagementView):
    viewname = 'download'

    def test_GET_no_album_or_photo_parameter(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_GET_photo(self):
        url = self.url + f'?photo={self.photo.slug}'

        response = self.client.get(url)

        self.assertEqual(response.get('Content-Disposition'), f"attachment; filename=\"{self.dummy_photo_title}.jpg\"")

    def test_GET_photo_does_not_exosts(self):
        url = self.url + f'?photo={self.photo.slug}dkofkgopdsko'

        response = self.client.get(url)

        self.assertEqual(response.status_code, 204)

    def test_GET_photo_is_private_not_authorised(self):
        url = self.url + f'?photo={self.private_photo.slug}'

        response = self.client.get(url)

        self.assertEqual(response.status_code, 204)

    def test_GET_album_not_authorised(self):
        url = self.url + f'?album={self.album.slug}'

        response = self.client.get(url)

        try:
            file = io.BytesIO(next(response.streaming_content))
            zipped_file = zipfile.ZipFile(file, 'r')

            self.assertIsNone(zipped_file.testzip())
            self.assertEqual(len(zipped_file.namelist()), 1)
        finally:
            zipped_file.close()
            file.close()

    def test_GET_album_authorised(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)
        url = self.url + f'?album={self.album.slug}'

        response = self.client.get(url)

        try:
            file = io.BytesIO(next(response.streaming_content))
            zipped_file = zipfile.ZipFile(file, 'r')
            self.assertIsNone(zipped_file.testzip())
            self.assertEqual(len(zipped_file.namelist()), 2)

        finally:
            zipped_file.close()
            file.close()

    def test_GET_album_does_not_exist(self):
        url = self.url + f'?album={self.album.slug}ksdopfkgosd'

        response = self.client.get(url)

        self.assertEqual(response.status_code, 204)

    def test_GET_album_private_not_authorised(self):
        self.album.is_private = True
        self.photo.is_private = True
        self.album.save()
        self.photo.save()
        url = self.url + f'?album={self.album.slug}'

        response = self.client.get(url)

        self.assertEqual(response.status_code, 204)

    def test_GET_album_is_empty(self):
        self.private_photo.delete()
        self.photo.delete()
        url = self.url + f'?album={self.album.slug}'

        response = self.client.get(url)

        self.assertEqual(response.status_code, 204)


class TestAddToFavorites(TestManagementView):
    viewname = 'add_to_favorites'

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_404(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_POST_not_specified_photo_or_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)

    def test_POST_not_existing_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'album': 'not_existing'})

        self.assertEqual(response.status_code, 404)

    def test_POST_owner_try_to_add_album_to_favorites(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.album.refresh_from_db()
        self.assertEqual(self.album.in_users_favorites.count(), 0)

    def test_POST_not_owner_try_to_add_album_to_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.album.refresh_from_db()
        self.assertIn(self.second_user, self.album.in_users_favorites.all())

    def test_POST_not_owner_try_to_add_private_album_to_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        self.album.is_private = True
        self.album.save()

        response = self.client.post(self.url, {'album': self.album.slug})

        self.album.refresh_from_db()
        self.assertEqual(self.album.in_users_favorites.count(), 0)

    def test_POST_redirected_to_specified_url(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'album': self.album.slug, 'next': reverse('about')})

        self.assertRedirects(response,reverse('about'))

    def test_POST_redirected_default(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.assertRedirects(response, reverse('main'))

    def test_POST_not_existing_photo(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'photo': 'not_existing'})

        self.assertEqual(response.status_code, 404)

    def test_POST_owner_try_to_add_photo_to_favorites(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'photo': self.album.slug})

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.in_users_favorites.count(), 0)

    def test_POST_not_owner_try_to_add_photo_to_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'photo': self.photo.slug})

        self.photo.refresh_from_db()
        self.assertIn(self.second_user, self.photo.in_users_favorites.all())

    def test_POST_not_owner_try_to_add_private_photo_to_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'photo': self.private_photo.slug})

        self.private_photo.refresh_from_db()
        self.assertEqual(self.private_photo.in_users_favorites.count(), 0)


class TestRemoveFromFavorites(TestManagementView):
    viewname = 'remove_from_favorites'

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_404(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_POST_not_specified_photo_or_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)

    def test_POST_not_existing_album(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'album': 'not_existing'})

        self.assertEqual(response.status_code, 404)

    def test_POST_not_existing_photo(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.post(self.url, {'photo': 'not_existing'})

        self.assertEqual(response.status_code, 404)

    def test_POST_delete_not_favorite_album_from_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.assertRedirects(response, reverse('main'))
        self.album.refresh_from_db()
        self.assertEqual(self.album.in_users_favorites.count(), 0)

    def test_POST_redirected_to_specified_url(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': self.album.slug, 'next': reverse('about')})

        self.assertRedirects(response, reverse('about'))

    def test_POST_redirected_default(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.assertRedirects(response, reverse('main'))

    def test_POST_delete_album_from_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        self.album.in_users_favorites.add(self.second_user)
        self.album.save()

        response = self.client.post(self.url, {'album': self.album.slug})

        self.album.refresh_from_db()
        self.assertEqual(self.album.in_users_favorites.count(), 0)

    def test_POST_delete_photo_from_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        self.photo.in_users_favorites.add(self.second_user)
        self.photo.save()

        response = self.client.post(self.url, {'photo': self.photo.slug})

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.in_users_favorites.count(), 0)


class TestSavePhotoToAlbum(TestManagementView):
    viewname = 'save_photo_to_album'

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_404(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_POST_no_data(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)

    def test_POST_wrong_data(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'data': 'jfdjifjig'})

        self.assertEqual(response.status_code, 400)

    def test_POST_not_not_existing_photo_and_album(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'data': 'photo:pslfpsldf, album:sdopkfopk'})

        self.assertEqual(response.status_code, 404)

    def test_POST_photo_is_not_in_user_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title='test_user2', owner=self.second_user)

        response = self.client.post(self.url, {'data': f'photo:{self.photo.slug}, album:{album.slug}'})

        self.assertEqual(response.status_code, 400)
        album.refresh_from_db()
        self.assertEqual(album.photos_set.count(), 0)

    def test_POST_same_photo_exists_in_this_album(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title='test_user2', owner=self.second_user)
        Photos.objects.create(title='test_photo_user2', album=album, original=self.photo.original)
        self.photo.in_users_favorites.add(self.second_user)
        self.photo.save()

        response = self.client.post(self.url, {'data': f'photo:{self.photo.slug}, album:{album.slug}'})

        self.assertEqual(response.status_code, 204)
        album.refresh_from_db()
        self.assertEqual(album.photos_set.count(), 1)

    def test_POST_successful_save(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title='test_user2', owner=self.second_user)
        self.photo.in_users_favorites.add(self.second_user)
        self.photo.save()

        response = self.client.post(self.url, {'data': f'photo:{self.photo.slug}, album:{album.slug}'})

        album.refresh_from_db()
        self.assertEqual(album.photos_set.count(), 1)

    def test_POST_redirected_to_specified_url(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title='test_user2', owner=self.second_user)
        self.photo.in_users_favorites.add(self.second_user)
        self.photo.save()

        response = self.client.post(self.url, {'data': f'photo:{self.photo.slug}, album:{album.slug}',
                                               'next': reverse('about')})

        self.assertRedirects(response, reverse('about'))

    def test_POST_redirected_default(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        album = Albums.objects.create(title='test_user2', owner=self.second_user)
        self.photo.in_users_favorites.add(self.second_user)
        self.photo.save()

        response = self.client.post(self.url, {'data': f'photo:{self.photo.slug}, album:{album.slug}'})

        self.assertRedirects(response, reverse('main'))


class TestSavAlbum(TestManagementView):
    viewname = 'save_album'

    def test_GET_not_authorised(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_GET_404(self):
        self.client.login(username=self.dummy_username, password=self.dummy_password)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_POST_album_not_specified(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)

    def test_POST_not_existing_or_private_album(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': 'utsdopkfopk'})

        self.assertEqual(response.status_code, 404)

    def test_POST_album_is_not_in_user_favorites(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)

        response = self.client.post(self.url, {'album': self.album.slug})

        self.assertEqual(response.status_code, 400)
        self.second_user.refresh_from_db()
        self.assertEqual(self.second_user.albums.count(), 0)

    def test_POST_successful_save(self):
        self.client.login(username=self.dummy_2_username, password=self.dummy_2_password)
        self.album.in_users_favorites.add(self.second_user)
        self.album.miniature = self.photo
        self.album.save()

        response = self.client.post(self.url, {'album': self.album.slug})

        self.second_user.refresh_from_db()
        self.assertEqual(self.second_user.albums.count(), 1)
        self.assertEqual(self.second_user.albums.first().photos_set.count(), 1)
        self.assertIsNotNone(self.second_user.albums.first().miniature)
        self.assertRedirects(response, reverse('user_albums', kwargs={'username_slug': self.second_user.username_slug}))
