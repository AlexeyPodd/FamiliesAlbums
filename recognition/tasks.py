from celery.utils.log import get_task_logger
from celery import shared_task

from .photos_handlers import FaceSearchingHandler, RelateFacesHandler, ComparingExistingAndNewPeopleHandler

logger = get_task_logger(__name__)


@shared_task
def face_searching_task(album_pk):
    logger.info(f"Starting to process {album_pk}. Now searching for faces on album's photos.")
    handler = FaceSearchingHandler(album_pk)
    handler.handle()
    return f"Search for faces on {album_pk} album's photos has been finished."


@shared_task
def relate_faces_task(album_pk):
    logger.info(f"Starting to relate founded faces on photos of album {album_pk}.")
    handler = RelateFacesHandler(album_pk)
    handler.handle()
    return f"Relating faces of {album_pk} album has been finished."


@shared_task
def compare_new_and_existing_people_task(album_pk):
    logger.info(f"Starting to compare created people of album {album_pk} with previously created people.")
    handler = ComparingExistingAndNewPeopleHandler(album_pk)
    handler.handle()
    return f"Comparing people of {album_pk} album with previously created people has been finished."
