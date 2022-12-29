import os
from urllib.parse import urlparse
from django.core.exceptions import ValidationError


def get_avatar_save_path(instance, filename):
    return f'avatars/{instance.username_slug}{os.path.splitext(filename)[-1]}'


def validate_facebook_url(value):
    hostname = urlparse(value).hostname
    if hostname != 'facebook.com' and hostname != 'www.facebook.com':
        raise ValidationError("Accepts only facebook link")


def validate_instagram_url(value):
    hostname = urlparse(value).hostname
    if hostname != 'instagram.com' and hostname != 'www.instagram.com':
        raise ValidationError("Accepts only instagram link")


def validate_telegram_url(value):
    hostname = urlparse(value).hostname
    if hostname != 't.me' and hostname != 'www.t.me':
        raise ValidationError("Accepts only telegram link")


def validate_whatsapp_url(value):
    hostname = urlparse(value).hostname
    if hostname != 'wa.me' and hostname != 'www.wa.me':
        raise ValidationError("Accepts only whatsapp link")
