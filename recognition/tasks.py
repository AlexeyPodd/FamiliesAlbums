from celery.utils.log import get_task_logger
from celery import shared_task

from .task_handlers import FaceSearchingHandler, RelateFacesHandler, ComparingExistingAndNewPeopleHandler, \
    SavingAlbumRecognitionDataToDBHandler, ClearTempDataHandler, SimilarPeopleSearchingHandler

logger = get_task_logger(__name__)

recognition_handlers = {handler.stage: handler for handler in [
    FaceSearchingHandler,
    RelateFacesHandler,
    ComparingExistingAndNewPeopleHandler,
    SavingAlbumRecognitionDataToDBHandler,
    ClearTempDataHandler,
    SimilarPeopleSearchingHandler,
]}


@shared_task
def recognition_task(object_pk: int, recognition_stage: int):
    handler = recognition_handlers[recognition_stage](object_pk)
    logger.info(handler.start_message)
    handler.handle()
    return handler.finish_message
