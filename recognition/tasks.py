from celery.utils.log import get_task_logger
from celery import shared_task

from .photos_handlers import ZeroStageHandler

logger = get_task_logger(__name__)


@shared_task
def zero_stage_process_album_task(album_pk):
    logger.info(f"Starting to process (stage zero) {album_pk}")
    handler = ZeroStageHandler(album_pk)
    handler.handle()
    return f"Album {album_pk} has passed zero stage (faces found)."
