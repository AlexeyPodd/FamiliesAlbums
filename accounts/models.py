from autoslug import AutoSlugField
from django.contrib.auth.models import AbstractUser
from django.db import models
from django_resized import ResizedImageField

from .utils import *


class User(AbstractUser):
    username_slug = AutoSlugField(populate_from='username', unique=True, db_index=True, verbose_name='User URL')
    email = models.EmailField(unique=True)
    avatar = ResizedImageField(upload_to=get_avatar_save_path, size=[600, 600], blank=True, null=True,
                               verbose_name="Avatar")
    about = models.CharField(max_length=255, blank=True, verbose_name="About user")
    facebook = models.URLField(blank=True,
                               validators=[validate_facebook_url],
                               verbose_name='facebook')
    instagram = models.URLField(blank=True,
                                validators=[validate_instagram_url],
                                verbose_name='instagram')
    telegram = models.URLField(blank=True,
                               validators=[validate_telegram_url],
                               verbose_name='telegram')
    whatsapp = models.URLField(blank=True,
                               validators=[validate_whatsapp_url],
                               verbose_name='whatsapp')

    def __str__(self):
        return self.username
