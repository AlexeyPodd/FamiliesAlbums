from celery.utils.log import get_task_logger
from celery import shared_task

from .models import Albums

logger = get_task_logger(__name__)


@shared_task
def album_deletion_task(album_pk):
    logger.info(f"Starting to delete album {album_pk}.")
    album = Albums.objects.get(pk=album_pk)
    for photo in album.photos_set.all():
        photo.delete()
    album.delete()
    return f"Deletion of album {album_pk} has been finished."
