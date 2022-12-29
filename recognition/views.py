from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin

from mainapp.models import Albums


class MainRecognitionView(LoginRequiredMixin, ListView):
    model = Albums
    template_name = 'recognition/main.html'
    context_object_name = 'albums'
    extra_context = {'title': 'Recognition',
                     'current_section': 'recognition_main',
                     }
    paginate_by = 12

    def get_queryset(self):
        queryset = self.model.objects.filter(owner__pk=self.request.user.pk)
        return queryset
