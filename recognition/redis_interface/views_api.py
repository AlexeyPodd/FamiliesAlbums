from .functional_api import RedisAPIFinished, RedisAPIStatus, RedisAPIPhotoSlug, \
    RedisAPIStage, RedisAPIProcessedPhotos, RedisAPIPhotoDataChecker, RedisAPIPhotoDataGetter, RedisAPIPhotoDataSetter, \
    RedisAPIAlbumDataGetter, RedisAPIAlbumDataSetter, RedisAPIPatternDataSetter, RedisAPIPatternDataGetter, \
    RedisAPIPatternDataChecker, RedisAPIPersonDataSetter, RedisAPIMatchesChecker, RedisAPIMatchesGetter, \
    RedisAPIMatchesSetter, RedisAPISearchGetter


class RedisAPIBaseView(RedisAPIStage, RedisAPIStatus):
    pass


class RedisAPIStage1View(
    RedisAPIBaseView,
    RedisAPIFinished,
    RedisAPIPhotoSlug,
    RedisAPIProcessedPhotos,
    RedisAPIPhotoDataChecker,
):
    pass


class RedisAPIStage2View(
    RedisAPIBaseView,
    RedisAPIPhotoDataGetter,
    RedisAPIPhotoDataSetter,
    RedisAPIPhotoDataChecker,
    RedisAPIPhotoSlug,
    RedisAPIFinished,
    RedisAPIProcessedPhotos,
):
    pass


class RedisAPIStage3View(
    RedisAPIBaseView,
    RedisAPIStatus,
    RedisAPIStatus,
):
    pass


class RedisAPIStage4View(
    RedisAPIBaseView,
    RedisAPIAlbumDataGetter,
    RedisAPIAlbumDataSetter,
    RedisAPIPatternDataGetter,
    RedisAPIPatternDataSetter,
    RedisAPIPatternDataChecker,
):
    pass


class RedisAPIStage5View(
    RedisAPIBaseView,
    RedisAPIAlbumDataGetter,
    RedisAPIPersonDataSetter,
):
    pass


class RedisAPIStage6View(
    RedisAPIBaseView,
    RedisAPIMatchesChecker,
):
    pass


class RedisAPIStage7View(
    RedisAPIBaseView,
    RedisAPIMatchesGetter,
    RedisAPIMatchesSetter,
    RedisAPIMatchesChecker,
    RedisAPIAlbumDataGetter,
):
    pass


class RedisAPIStage8View(
    RedisAPIBaseView,
    RedisAPIMatchesGetter,
    RedisAPIMatchesSetter,
    RedisAPIMatchesChecker,
):
    pass


class RedisAPIStage9View(
    RedisAPIBaseView,
    RedisAPIFinished,
):
    pass


class RedisAPIStageSearchView(RedisAPISearchGetter):
    pass
