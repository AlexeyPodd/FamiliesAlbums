import os

from celery.utils.log import get_task_logger
from celery import shared_task

from photoalbums.settings import TEMP_ROOT
from .supporters import RedisSupporter, DataDeletionSupporter
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


@shared_task
def clear_cache_and_delete_expired_temp_files():
    logger.info("Cache clearing and deletion of expire temp files started")
    temp_directories = os.listdir(TEMP_ROOT)
    for directory_name in temp_directories:
        if not RedisSupporter.check_album_in_processing(directory_name):
            DataDeletionSupporter.delete_temp_directory(directory_name)

    DataDeletionSupporter.clear_cache()

    return "Cache clearing and deletion of expire temp files finished"
