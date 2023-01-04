from celery.utils.log import get_task_logger
from celery import shared_task

from .photos_processes import *

logger = get_task_logger(__name__)


@shared_task
def zero_stage_process_album_task(album_slug):
    logger.info(f"Starting to process (stage zero) {album_slug}")
    return find_faces_on_photos(album_slug=album_slug)
