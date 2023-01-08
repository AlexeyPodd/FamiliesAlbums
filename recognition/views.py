import os
import redis

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_protect
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.views.generic.edit import FormMixin

from mainapp.models import *
from .forms import VerifyFramesForm
from .tasks import zero_stage_process_album_task
from photoalbums.settings import REDIS_HOST, REDIS_PORT


redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)


class AlbumsRecognitionView(LoginRequiredMixin, ListView):
    model = Albums
    template_name = 'recognition/albums.html'
    context_object_name = 'albums'
    extra_context = {'title': 'Recognition - Albums',
                     }
    paginate_by = 12

    def get_queryset(self):
        queryset = self.model.objects.filter(owner__pk=self.request.user.pk).annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False)),
            processed_photos=Count('photos', filter=(Q(photos__is_private=False) & Q(photos__faces_extracted=True)))
        )
        return queryset


class AlbumProcessingConfirmView(LoginRequiredMixin, DetailView):
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/processing_confirm.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': f'Album \"{self.object}\"',
        })
        return context

    def get_queryset(self):
        queryset = self.model.objects.filter(owner__pk=self.request.user.pk).annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False)),
            processed_photos=Count('photos', filter=(Q(photos__is_private=False) & Q(photos__faces_extracted=True)))
        )
        return queryset


@csrf_protect
@login_required
def zero_stage_album_processing_view(request, album_slug):
    if request.method != 'POST':
        raise Http404
    album = Albums.objects.get(slug=album_slug)
    if request.user.username_slug != album.owner.username_slug:
        raise Http404

    if not redis_instance.exists(f"album_{album.pk}"):
        photos_slugs = [photo.slug for photo in album.photos_set.filter(is_private=False,
                                                                        faces_extracted=False)]
        redis_instance.rpush(f"album_{album.pk}_photos", *photos_slugs)

    if not (redis_instance.hget(f"album_{album.pk}", "current_stage") == 0 and
            redis_instance.hget(f"album_{album.pk}", "status") == "processing"):
        redis_instance.hset(f"album_{album.pk}", "current_stage", 0)
        redis_instance.hset(f"album_{album.pk}", "status", "processing")
        redis_instance.hset(f"album_{album.pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{album.pk}", 86_400)
        zero_stage_process_album_task.delay(album.pk)

    return redirect('process_waiting', album_slug=album_slug)


class AlbumProcessWaitingView(LoginRequiredMixin, DetailView):
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/process_waiting.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        status = redis_instance.hget(f"album_{self.object.pk}", "status")

        if current_stage is None:
            raise Http404
        elif current_stage == 0 and status == "processing":
            number_of_processed_photos = redis_instance.hget(f"album_{self.object.pk}", "number_of_processed_photos")
            if number_of_processed_photos is None:
                number_of_processed_photos = 0

            context.update({
                'title': f'Album \"{self.object}\" - waiting',
                'is_ready': False,
                'number_of_processed_photos': number_of_processed_photos,
                'first_photo_slug': redis_instance.lindex(f"album_{self.object.pk}_photos", 0),
            })
        else:
            context.update({
                'title': f'Album \"{self.object}\" - ready to continue',
                'is_ready': True,
                'first_photo_slug': redis_instance.lindex(f"album_{self.object.pk}_photos", 0),
            })

        return context

    def get_queryset(self):
        queryset = self.model.objects.filter(owner__pk=self.request.user.pk).annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False))
        )

        return queryset


class AlbumVerifyFramesView(LoginRequiredMixin, FormMixin, DetailView):
    model = Photos
    template_name = 'recognition/verify_frames.html'
    context_object_name = 'photo'
    form_class = VerifyFramesForm
    slug_url_kwarg = 'photo_slug'

    def get(self, request, *args, **kwargs):
        self.album = Albums.objects.get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        if not request.user.is_authenticated or request.user.username_slug != self.album.owner.username_slug or \
                self.object.is_private:
            raise Http404

        if redis_instance.hget(f"album_{self.album.pk}", "current_stage") is None or \
                int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) < 1 and \
                redis_instance.hget(f"album_{self.album.pk}", "status") != "completed":
            raise Http404

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.album = Albums.objects.get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        if not request.user.is_authenticated or request.user.username_slug != self.album.owner.username_slug or \
                self.object.is_private:
            raise Http404

        if redis_instance.hget(f"album_{self.album.pk}", "current_stage") is None or \
                int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) < 1 and \
                redis_instance.hget(f"album_{self.album.pk}", "status") != "completed":
            raise Http404

        # Base Form method post
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'faces_amount': redis_instance.hlen(f"photo_{self.object.pk}") // 2})

        return kwargs

    def form_valid(self, form):
        self._delete_wrong_data(form)
        self._set_correct_status()
        return super().form_valid(form)

    def _delete_wrong_data(self, form):
        for name, to_delete in form.cleaned_data.items():
            if to_delete:
                redis_instance.hdel(f"photo_{self.object.pk}", name + "_location", name + "_encoding")

    def _set_correct_status(self):
        redis_instance.hincrby(f"album_{self.album.pk}", "number_of_processed_photos")

        if int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == 0 and \
                self.object.slug == redis_instance.lindex(f"album_{self.object.pk}_photos", 0):
            redis_instance.hset(f"album_{self.album.pk}", "current_stage", 1)
            redis_instance.hset(f"album_{self.album.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.album.pk}", 86_400)
        elif int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == 1 and \
                self.object.slug == redis_instance.lindex(f"album_{self.object.album.pk}_photos", -1):
            redis_instance.hset(f"album_{self.album.pk}", "current_stage", 1)
            redis_instance.hset(f"album_{self.album.pk}", "status", "completed")
            redis_instance.hset(f"album_{self.album.pk}", "number_of_processed_photos", 0)
            redis_instance.expire(f"album_{self.album.pk}", 86_400)

    def get_success_url(self):
        if self.object.slug == redis_instance.lindex(f"album_{self.object.album.pk}_photos", -1):
            return reverse_lazy('recognition_main')
        else:
            next_photo_slug = redis_instance.lindex(
                f"album_{self.object.album.pk}_photos",
                redis_instance.lpos(f"album_{self.object.album.pk}_photos", self.object.slug) + 1,
            )
            return reverse_lazy('verify_frames', kwargs={'album_slug': self.album.slug, 'photo_slug': next_photo_slug})

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.album}\" - verifying frames',
            'public_photos': self.album.photos_set.all().count(),
            'current_photo_number': int(redis_instance.hget(f"album_{self.album.pk}", "number_of_processed_photos")) + 1,
            'is_last_photo': self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", -1),
            'photo_with_frames_url': os.path.join('/media/temp_photos',
                                                  f'album_{self.album.pk}',
                                                  f"photo_{self.object.pk}.jpg"),
        })

        return context
