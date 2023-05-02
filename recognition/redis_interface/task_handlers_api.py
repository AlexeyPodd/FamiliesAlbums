from .functional_api import RedisAPIStage, RedisAPIStatus, RedisAPIProcessedPhotos, RedisAPIAlbumDataChecker, \
    RedisAPIFullAlbumPeopleDataGetter, RedisAPIPhotoDataGetter, RedisAPIPersonDataCreator, RedisAPIPersonDataSetter, \
    RedisAPIFinished, RedisAPIMatchesSetter, RedisAPIPatternDataSetter, RedisAPIPhotoSlug, RedisAPIPhotoDataSetter, \
    RedisAPISearchSetter


class RedisAPIBaseHandler(
    RedisAPIStage,
    RedisAPIStatus,
    RedisAPIProcessedPhotos,
):
    pass


class RedisAPIBaseLateStageHandler(
    RedisAPIBaseHandler,
    RedisAPIAlbumDataChecker,
    RedisAPIFullAlbumPeopleDataGetter,
    RedisAPIPersonDataCreator,
    RedisAPIPhotoDataGetter,
    RedisAPIPersonDataSetter,
):
    pass


class RedisAPIStage1Handler(
    RedisAPIBaseHandler,
    RedisAPIPhotoSlug,
    RedisAPIPhotoDataSetter,
    RedisAPIFinished,
):
    pass


class RedisAPIStage3Handler(
    RedisAPIBaseHandler,
    RedisAPIPhotoDataGetter,
    RedisAPIPatternDataSetter,
):
    pass


class RedisAPIStage6Handler(
    RedisAPIBaseLateStageHandler,
    RedisAPIMatchesSetter,
):
    pass


class RedisAPIStage9Handler(
    RedisAPIBaseLateStageHandler,
    RedisAPIFinished,
):
    pass


class RedisAPISearchHandler(RedisAPISearchSetter):
    pass
