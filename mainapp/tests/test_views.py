from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User
from mainapp.models import Albums, Photos
from photoalbums.settings import ALBUMS_AMOUNT_LIMIT


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
        'album_slug': dummy_album_title,
        'photo_slug': dummy_photo_title,
    }
    url_variables = []

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
                if 'photo_slug' in cls.url_variables:
                    cls.photo = Photos.objects.create(title=cls.dummy_photo_title, album=cls.album)

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
