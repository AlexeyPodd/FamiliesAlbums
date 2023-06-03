import base64

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

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
    test_image = SimpleUploadedFile(
            f"{dummy_photo_title}.jpeg",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAUA" +
                             "AAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO" +
                             "9TXL0Y4OHwAAAABJRU5ErkJggg=="), content_type="image/jpeg")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cache.clear()

        if 'username_slug' in cls.url_variables:
            cls.user = User.objects.create_user(
                username=cls.dummy_username,
                password=cls.dummy_password,
                email=cls.dummy_email,
            )
            cls.second_user = User.objects.create_user(
                username=cls.dummy_2_username,
                password=cls.dummy_2_password,
                email=cls.dummy_2_email,
            )
            if 'album_slug' in cls.url_variables:
                cls.album = Albums.objects.create(title=cls.dummy_album_title, owner=cls.user)
                cls.photo = Photos.objects.create(title=cls.dummy_photo_title, album=cls.album, original=cls.test_image)
                cls.private_photo = Photos.objects.create(title=cls.dummy_photo_title, album=cls.album,
                                                          is_private=True, original=cls.test_image)

        url_kwargs = {key: cls.full_kwargs.get(key) for key in cls.url_variables}
        cls.url = reverse(viewname=cls.viewname, kwargs=url_kwargs)

    def setUp(self):
        self.client = Client()


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
