from celery.utils.log import get_task_logger
from celery import shared_task

from .task_handlers import FaceSearchingHandler, RelateFacesHandler, ComparingExistingAndNewPeopleHandler, \
    SavingAlbumRecognitionDataToDBHandler, ClearTempDataHandler

logger = get_task_logger(__name__)
recognition_handlers = {1: FaceSearchingHandler,
                        3: RelateFacesHandler,
                        6: ComparingExistingAndNewPeopleHandler,
                        9: SavingAlbumRecognitionDataToDBHandler,
                        -1: ClearTempDataHandler}


@shared_task
def recognition_task(album_pk: int, recognition_stage: int):
    handler = recognition_handlers[recognition_stage](album_pk)
    logger.info(handler.start_message)
    handler.handle()
    return handler.finish_message


@shared_task
def print_task(message: str):
    return message
