from django.http import Http404

from recognition.redis_interface.views_api import RedisAPIBaseView


class RecognitionMixin:
    redisAPI = RedisAPIBaseView

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def _get_object_and_make_checks(self, queryset=None, waiting_task=False):
        self.object = self.get_object(queryset=queryset)
        self._check_access_right()
        self._check_recognition_stage(waiting_task=waiting_task)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug or self.object.is_private:
            raise Http404

    def _check_recognition_stage(self, waiting_task):
        stage = self.redisAPI.get_stage_or_404(self.object.pk)
        status = self.redisAPI.get_status(self.object.pk)

        if waiting_task:
            if not (stage == self.recognition_stage and status == "processing" or
                    stage in (self.recognition_stage, self.recognition_stage + 1) and status == "completed"):
                raise Http404
        else:
            if not (stage == self.recognition_stage and status == "processing" or
                    stage == self.recognition_stage - 1 and status == "completed"):
                raise Http404

    def get_queryset(self):
        return self.model.objects.select_related('owner').filter(owner__pk=self.request.user.pk)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'top_heading': "Recognition processing album's photos"})
        return context


class ManualRecognitionMixin(RecognitionMixin):
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
