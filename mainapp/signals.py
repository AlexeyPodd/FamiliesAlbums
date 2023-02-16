import os

from django.db.models import Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from photoalbums.settings import BASE_DIR
from .models import Photos
from recognition.models import Faces


@receiver(pre_delete, sender=Photos)
def photos_delete(sender, instance, **kwargs):
    # Deletion of image file
    if instance.original is not None and\
            not Photos.objects.filter(Q(original=instance.original) & ~ Q(pk=instance.pk)).exists():

        directory = os.path.dirname(os.path.abspath(os.path.join(BASE_DIR, instance.original.url[1:])))
        instance.original.delete()

        # removing empty folders
        while os.path.basename(directory) != 'media':
            try:
                os.rmdir(directory)
                directory = os.path.dirname(directory)
            except OSError:
                break

    # Faces set deletion
    for face in instance.faces_set.all():
        Faces.objects.get(pk=face.pk).delete()
