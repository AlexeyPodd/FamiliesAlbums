import os

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from photoalbums.settings import BASE_DIR
from .models import Photos


@receiver(pre_delete, sender=Photos)
def photos_delete(sender, instance, **kwargs):
    if instance.original is not None and not Photos.objects.filter(original=instance.original).exists():
        directory = os.path.dirname(os.path.abspath(os.path.join(BASE_DIR, instance.original.url[1:])))
        instance.original.delete()

        # removing empty folders
        while os.path.basename(directory) != 'media':
            try:
                os.rmdir(directory)
                directory = os.path.dirname(directory)
            except OSError:
                break
