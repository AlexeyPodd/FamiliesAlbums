from django.http import Http404

from recognition.supporters import RedisSupporter


class RecognitionMixin:
    def _get_object_and_make_checks(self, queryset=None, waiting_task=False):
        self.object = self.get_object(queryset=queryset)
        self._check_access_right()
        self._check_recognition_stage(waiting_task=waiting_task)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug or self.object.is_private:
            raise Http404

    def _check_recognition_stage(self, waiting_task):
        stage = RedisSupporter.get_stage_or_404(self.object.pk)

        if waiting_task:
            if stage != self.recognition_stage:
                raise Http404
        else:
            status = RedisSupporter.get_status(self.object.pk)
            if not (stage == self.recognition_stage and status == "processing" or
                    stage == self.recognition_stage - 1 and status == "completed"):
                raise Http404
