from api_v1.data_extractors import FacesInPhotosExtractor, PatternsFacesExtractor, PatternsForGroupingExtractor, \
    TechPairsExtractor, SinglePeopleExtractor
from recognition.redis_interface.functional_api import RedisAPIStage, RedisAPIStatus, RedisAPIFinished


class RecognitionStateCollector:
    """Base cass for collecting data of album processing."""
    data_extractors = {extractor.completed_stage: extractor for extractor in [
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
        if self.status != "completed" or self.finished or self.stage not in self.data_extractors:
            return

        extractor = self.data_extractors[self.stage](self.album_pk, self.request)
        self.data = extractor.get_data()
