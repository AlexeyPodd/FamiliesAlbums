from api_v1.data_extractors import FacesInPhotosExtractor, PatternsFacesExtractor, PatternsForGroupingExtractor, \
    TechPairsExtractor, SinglePeopleExtractor, ProcessedPhotosAmountExtractor
from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus, RedisAPIFinished


class RecognitionStateCollector:
    """Base cass for collecting data of album processing."""
    data_extractors = {extractor.completed_stage: extractor for extractor in [
        ProcessedPhotosAmountExtractor,
        FacesInPhotosExtractor,
        PatternsFacesExtractor,
        PatternsForGroupingExtractor,
        TechPairsExtractor,
        SinglePeopleExtractor,
    ]}

    def __init__(self, album_pk: int, request=None):
        self.album_pk = album_pk
        self.request = request
        self.stage = RedisAPIStage.get_stage(album_pk)
        self.status = RedisAPIStatus.get_status(album_pk)
        self.finished = RedisAPIFinished.get_finished_status(album_pk) or False
        self.data = None

    def collect(self):
        if self.finished:
            return

        if isinstance(self.stage, int) and self.stage <= 1 and self.status != "completed":
            extractor_class = self.data_extractors[0]
        elif self.status == "completed" and self.stage in self.data_extractors:
            extractor_class = self.data_extractors[self.stage]
        else:
            return

        extractor = extractor_class(self.album_pk, self.request)
        self.data = extractor.get_data()
