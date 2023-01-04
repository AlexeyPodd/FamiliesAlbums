from django.db import models
from django.urls import reverse
from django_extensions.db.fields import AutoSlugField

from photoalbums.settings import AUTH_USER_MODEL
from .utils import get_photo_save_path


class Albums(models.Model):
    title = models.CharField(max_length=127, verbose_name='Title')
    slug = AutoSlugField(populate_from=['owner__username_slug', 'title'], db_index=True, verbose_name='URL')
    date_start = models.DateField(blank=True, null=True, verbose_name='Photo date start')
    date_end = models.DateField(blank=True, null=True, verbose_name='Photo date end')
    location = models.CharField(max_length=63, blank=True, verbose_name='Location')
    description = models.CharField(max_length=1023, blank=True, verbose_name='Description')
    time_create = models.DateTimeField(auto_now_add=True, verbose_name="Date of creation")
    time_update = models.DateTimeField(auto_now=True, verbose_name="Last update date")
    owner = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owner', verbose_name='Owner')
    in_users_favorites = models.ManyToManyField(AUTH_USER_MODEL, blank=True, related_name='album_in_users_favorites', verbose_name="In Users' Favorites")
    is_private = models.BooleanField(default=False, verbose_name='Privacy')
    miniature = models.OneToOneField('Photos', blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Miniature')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setattr(self, 'original_is_private', getattr(self, 'is_private'))

    def get_absolute_url(self):
        return reverse('album', kwargs={'username_slug': self.owner.username_slug, 'album_slug': self.slug})

    # def count_processed_photos(self):
    #     return self.photos_set.

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'User Album'
        verbose_name_plural = 'Users Albums'
        ordering = ['time_create']


class Photos(models.Model):
    title = models.CharField(max_length=127, verbose_name='Title')
    slug = AutoSlugField(populate_from='title', unique=True, db_index=True, verbose_name='URL')
    date_start = models.DateField(blank=True, null=True, verbose_name='Photo date start')
    date_end = models.DateField(blank=True, null=True, verbose_name='Photo date end')
    location = models.CharField(max_length=63, blank=True, verbose_name='Location')
    description = models.CharField(max_length=1023, blank=True, verbose_name='Description')
    time_create = models.DateTimeField(auto_now_add=True, verbose_name="Date of creation")
    time_update = models.DateTimeField(auto_now=True, verbose_name="Last update date")
    is_private = models.BooleanField(default=False, verbose_name='Privacy')
    album = models.ForeignKey('Albums', on_delete=models.CASCADE, verbose_name='Album')
    original = models.ImageField(upload_to=get_photo_save_path, verbose_name="Original")
    in_users_favorites = models.ManyToManyField(AUTH_USER_MODEL, blank=True, related_name='photo_in_users_favorites', verbose_name="In Users' Favorites")
    faces_extracted = models.BooleanField(default=False, verbose_name='Faces Extracted')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setattr(self, 'original_is_private', getattr(self, 'is_private'))

    def get_absolute_url(self):
        return reverse('photo', kwargs={'photo_slug': self.slug, 'username_slug': self.album.owner.username_slug, 'album_slug': self.album.slug})

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'User Photo'
        verbose_name_plural = 'Users Photos'
        ordering = ['time_create']
