from .functional_api import RedisAPIStage, RedisAPIStatus, RedisAPIProcessedPhotos, RedisAPIAlbumDataChecker, \
    RedisAPIFullAlbumPeopleDataGetter, RedisAPIPhotoDataGetter, RedisAPIPersonDataCreator, RedisAPIPersonDataSetter, \
    RedisAPIFinished, RedisAPIMatchesSetter, RedisAPIPatternDataSetter, RedisAPIPhotoSlug, RedisAPIPhotoDataSetter, \
    RedisAPISearchSetter, RedisAPIAlbumDataSetter, RedisAPIMatchesChecker


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
    RedisAPIAlbumDataSetter,
):
    pass


class RedisAPIStage6Handler(
    RedisAPIBaseLateStageHandler,
    RedisAPIMatchesSetter,
    RedisAPIMatchesChecker,
):
    pass


class RedisAPIStage9Handler(
    RedisAPIBaseLateStageHandler,
    RedisAPIFinished,
):
    pass


class RedisAPISearchHandler(RedisAPISearchSetter):
    pass
