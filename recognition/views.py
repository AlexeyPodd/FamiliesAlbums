import os
import pickle
import re

from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy, reverse
from django.views.decorators.csrf import csrf_protect
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.views.generic.edit import FormMixin

from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos, Albums
from .data_classes import PatternData, FaceData
from .forms import *
from .models import Faces, People
from .tasks import recognition_task, print_task
from photoalbums.settings import REDIS_DATA_EXPIRATION_SECONDS, MEDIA_ROOT, BASE_DIR
from .utils import set_album_photos_processed, redis_instance, redis_instance_raw
from .mixin_views import RecognitionMixin


def return_face_image_view(request, face_slug):
    face = Faces.objects.select_related('photo').get(slug=face_slug)
    if not request.user.is_authenticated or face.photo.is_private:
        raise Http404
    photo_img = Image.open(os.path.join(BASE_DIR, face.photo.original.url[1:]))
    top, right, bottom, left = face.loc_top, face.loc_right, face.loc_bot, face.loc_left
    face_img = photo_img.crop((left, top, right, bottom))
    response = HttpResponse(content_type='image/jpg')
    face_img.save(response, "JPEG")
    return response


def return_photo_with_framed_faces(request, photo_slug):
    photo = Photos.objects.select_related('album__owner').get(slug=photo_slug)

    if not request.user.is_authenticated or request.user.pk != photo.album.owner.pk or photo.is_private:
        raise Http404

    # Loading faces locations from redis
    faces_locations = []
    i = 1
    while redis_instance.hexists(f"photo_{photo.pk}", f"face_{i}_location"):
        faces_locations.append(pickle.loads(redis_instance_raw.hget(f"photo_{photo.pk}", f"face_{i}_location")))
        i += 1

    # Drawing
    image = Image.open(os.path.join(BASE_DIR, photo.original.url[1:]))
    draw = ImageDraw.Draw(image)
    for i, location in enumerate(faces_locations, 1):
        top, right, bottom, left = location
        draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=4)
        fontsize = (bottom - top) // 3
        font = ImageFont.truetype("arialbd.ttf", fontsize)
        draw.text((left, top), str(i), fill=(255, 0, 0), font=font)
    del draw

    response = HttpResponse(content_type='image/jpg')
    image.save(response, "JPEG")
    return response


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

    def get(self, request, *args, **kwargs):
        self.object = Albums.objects.select_related('owner').annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False))
        ).get(slug=kwargs['album_slug'])

        self._check_access_right()

        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        instructions = [
            "Processing album photos will take some time. After that, you will need to verify the result.",
            "If you do not complete the procedure, the result will NOT be saved.",
        ]

        context.update({
            'title': f'Album \"{self.object}\" - recognition',
            'button_label': "Start people recognition",
            'instructions': instructions,
        })
        return context

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        if self.object.is_private or self.object.public_photos == 0:
            raise Http404


@csrf_protect
@login_required
def find_faces_view(request, album_slug):
    if request.method != 'POST':
        raise Http404
    album = Albums.objects.select_related('owner').get(slug=album_slug)

    if request.user.username_slug != album.owner.username_slug:
        raise Http404

    redis_instance.hset(f"album_{album.pk}", "current_stage", 0)
    redis_instance.hset(f"album_{album.pk}", "status", "processing")
    redis_instance.expire(f"album_{album.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    recognition_task.delay(album.pk, 1)

    return redirect('frames_waiting', album_slug=album_slug)


class AlbumFramesWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 1
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_frames.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self._check_access_right()
        self.check_recognition_stage()

        if self._photos_processed_and_no_faces_found():
            self._set_no_faces_and_clear(album_pk=self.object.pk)
            return redirect('no_faces', album_slug=self.object.slug)

        return super().get(request, *args, **kwargs)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404

        if current_stage not in (self.recognition_stage - 1, self.recognition_stage):
            raise Http404

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            number_of_processed_photos = int(redis_instance.hget(f"album_{self.object.pk}",
                                                                 "number_of_processed_photos"))
        except TypeError:
            number_of_processed_photos = 0

        status = redis_instance.hget(f"album_{self.object.pk}", "status")
        if status == "processing":
            is_ready = False
            instructions = [
                "We are searching for faces on photos of this album. This may take some time.",
                "Please refresh this page until you see that all the photos have been processed.",
                "We will need you to do some verification of the result.",
            ]
            title = f'Album \"{self.object}\" - waiting'
        else:
            is_ready = True
            instructions = [
                "We are ready to continue. You can press the button!",
            ]
            title = f'Album \"{self.object}\" - ready to continue'

        first_photo_slug = redis_instance.lindex(f"album_{self.object.pk}_photos", 0)

        context.update({
            'heading': "Searching for faces on album's photos",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': instructions,
            'is_ready': is_ready,
            'title': title,
            'number_of_processed_photos': number_of_processed_photos,
            'button_label': "Verify frames",
            'next': 'verify_frames',
            'photo_slug': first_photo_slug,
        })

        return context

    def _photos_processed_and_no_faces_found(self):
        pks = tuple(map(lambda p: p.pk, self.object.photos_set.all()))
        for pk in pks:
            if not redis_instance.exists(f"photo_{pk}"):
                return False

        for pk in pks:
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                return False

        return True

    def get_queryset(self):
        queryset = self.model.objects.select_related('owner').filter(owner__pk=self.request.user.pk).annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False))
        )

        return queryset


class AlbumVerifyFramesView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    recognition_stage = 2
    model = Photos
    template_name = 'recognition/verify_frames.html'
    context_object_name = 'photo'
    form_class = VerifyFramesForm
    slug_url_kwarg = 'photo_slug'

    def get(self, request, *args, **kwargs):
        self.album = Albums.objects.get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        self._check_access_right()
        self._check_recognition_stage()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.album = Albums.objects.select_related('owner').prefetch_related('photos_set').get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        self._check_access_right()
        self._check_recognition_stage()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.album.owner.username_slug or self.object.is_private:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.album.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == self.recognition_stage and
                redis_instance.hget(f"album_{self.album.pk}", "status") == "processing" or
                current_stage == self.recognition_stage - 1 and
                redis_instance.hget(f"album_{self.album.pk}", "status") == "completed"):
            raise Http404

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'faces_amount': int(redis_instance.hget(f"photo_{self.object.pk}", "faces_amount"))})

        return kwargs

    def form_valid(self, form):
        self._delete_wrong_data(form)
        self._renumber_faces()
        self._set_correct_status()

        # If this photo is the last one
        if self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", -1):
            self._count_verified_faces()
            if self._faces_amount == 0:
                self._set_no_faces_and_clear(album_pk=self.album.pk)
            else:
                self._get_next_stage()
                self._start_celery_task(self._next_stage)

        return super().form_valid(form)

    def _delete_wrong_data(self, form):
        for name, to_delete in form.cleaned_data.items():
            if to_delete:
                redis_instance.hdel(f"photo_{self.object.pk}", name + "_location", name + "_encoding")

    def _renumber_faces(self):
        faces_amount = int(redis_instance.hget(f"photo_{self.object.pk}", "faces_amount"))
        count = 0
        for i in range(1, faces_amount + 1):
            if redis_instance.hexists(f"photo_{self.object.pk}", f"face_{i}_location"):
                count += 1
                if count != i:
                    redis_instance.hset(f"photo_{self.object.pk}",
                                        f"face_{count}_location",
                                        redis_instance_raw.hget(f"photo_{self.object.pk}", f"face_{i}_location"))
                    redis_instance.hdel(f"photo_{self.object.pk}", f"face_{i}_location")
                    redis_instance.hset(f"photo_{self.object.pk}",
                                        f"face_{count}_encoding",
                                        redis_instance_raw.hget(f"photo_{self.object.pk}", f"face_{i}_encoding"))
                    redis_instance.hdel(f"photo_{self.object.pk}", f"face_{i}_encoding")

        redis_instance.hset(f"photo_{self.object.pk}", "faces_amount", count)

    def _get_next_stage(self):
        another_album_processed = Faces.objects.filter(
            photo__album__owner__username_slug=self.album.owner.username_slug,
        ).exclude(photo__album__pk=self.album.pk).exists()

        if self._faces_amount == 1 and another_album_processed:
            self._next_stage = 6
        elif self._faces_amount == 1:
            self._next_stage = 9
        else:
            self._next_stage = 3

    def _set_correct_status(self):
        redis_instance.hincrby(f"album_{self.album.pk}", "number_of_processed_photos")

        if int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == self.recognition_stage - 1 and \
                self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", 0):
            redis_instance.hset(f"album_{self.album.pk}", "current_stage", self.recognition_stage)
            redis_instance.hset(f"album_{self.album.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)
        if int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == self.recognition_stage and \
                self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", -1):
            redis_instance.hset(f"album_{self.album.pk}", "status", "completed")
            redis_instance.hset(f"album_{self.album.pk}", "number_of_processed_photos", 0)
            redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def get_success_url(self):
        if self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", -1):
            if self._faces_amount == 0:
                return reverse_lazy('no_faces', kwargs={'album_slug': self.album.slug})
            elif self._faces_amount == 1:
                if self._next_stage == 9:
                    return reverse_lazy('save_waiting', kwargs={'album_slug': self.album.slug})
                elif self._next_stage == 6:
                    return reverse_lazy('people_waiting', kwargs={'album_slug': self.album.slug})
                else:
                    raise Http404
            else:
                return reverse_lazy('patterns_waiting', kwargs={'album_slug': self.album.slug})
        else:
            next_photo_slug = redis_instance.lindex(
                f"album_{self.album.pk}_photos",
                redis_instance.lpos(f"album_{self.album.pk}_photos", self.object.slug) + 1,
            )
            return reverse_lazy('verify_frames', kwargs={'album_slug': self.album.slug, 'photo_slug': next_photo_slug})

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        current_photo_number = int(redis_instance.hget(f"album_{self.album.pk}", "number_of_processed_photos")) + 1
        photos_with_faces = redis_instance.llen(f"album_{self.album.pk}_photos")
        instructions = [
            "Please mark the faces of children under 10 and objects that are not faces.",
            "They will be removed.",
        ]
        if self.object.slug == redis_instance.lindex(f"album_{self.album.pk}_photos", -1):
            button_label = "Next stage"
        else:
            button_label = "Next photo"

        context.update({
            'title': f'Album \"{self.album}\" - verifying frames',
            'heading': f"Verifying photo {self.object.title} ({current_photo_number}/{photos_with_faces})",
            'instructions': instructions,
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'button_label': button_label,
        })

        return context

    def _start_celery_task(self, next_stage):
        redis_instance.hset(f"album_{self.album.pk}", "current_stage", next_stage)
        redis_instance.hset(f"album_{self.album.pk}", "status", "processing")
        redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        recognition_task.delay(self.album.pk, next_stage)

    def _count_verified_faces(self):
        count = 0
        for pk in map(lambda p: p.pk, self.album.photos_set.all()):
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                count += 1

        self._faces_amount = count


class AlbumPatternsWaitingView(LoginRequiredMixin, DetailView):
    recognition_stage = 3
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_patterns.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self.status = redis_instance.hget(f"album_{self.object.pk}", "status")

        return super().get(request, *args, **kwargs)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if current_stage != self.recognition_stage:
            raise Http404

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            instructions = [
                "Now verified faces are combined into patterns.",
                "This should take no more than a moment.",
                "Please refresh this page now.",
            ]

        else:
            title = f'Album \"{self.object}\" - ready to continue'
            is_ready = True
            instructions = [
                "Patterns of faces has created, we are ready to continue.",
                "You can press the button!",
            ]

        context.update({
            'title': title,
            'is_ready': is_ready,
            'heading': "Recognizing faces. Creating patterns.",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': instructions,
            'button_label': "Verify results",
            'next': 'verify_patterns',
        })

        return context


class AlbumVerifyPatternsView(LoginRequiredMixin, FormMixin, DetailView):
    recognition_stage = 4
    template_name = 'recognition/verify_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = BaseVerifyPatternForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self._set_faces_amounts()
        self._set_number_of_verified_patterns()

        # If all patterns have only one face each
        if all(map(lambda x: x == 1, self._faces_amounts[self._number_of_verified_patterns:])):
            self._prepare_to_redirect_to_next_stage()
            return redirect('group_patterns', album_slug=self.object.slug)

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._number_of_verified_patterns,
                                            album_pk=self.object.pk)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self._set_faces_amounts()
        self._set_number_of_verified_patterns()

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(request.POST, faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._number_of_verified_patterns,
                                            album_pk=self.object.pk)

        form = self.get_form()
        if self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == self.recognition_stage - 1 and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == self.recognition_stage and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

    def _prepare_to_redirect_to_next_stage(self):
        self._register_verified_patterns_to_redis(len(self._faces_amounts))
        self._set_single_face_is_central()
        self._set_correct_status(all_patterns_have_single_faces=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - verifying patterns',
            'formset': self.formset,
            'heading': "Verifying patterns of people's faces.",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': ["Please mark odd faces, that do not fit the majority in each row."],
            'button_label': "Confirm",
        })

        return context

    def _set_faces_amounts(self):
        amounts = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_pattern_{i}"):
            amounts.append(int(redis_instance.hget(f"album_{self.object.pk}_pattern_{i}", "faces_amount")))
            i += 1
        self._faces_amounts = tuple(amounts)

    def _set_number_of_verified_patterns(self):
        try:
            self._number_of_verified_patterns = int(redis_instance.hget(f"album_{self.object.pk}",
                                                                        "number_of_verified_patterns"))
        except TypeError:
            self._number_of_verified_patterns = 0

    def form_valid(self, form):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self.object.pk}/patterns')
        old_patterns_amount = len(self._faces_amounts)
        patterns_amount = self._replace_odd_faces_to_new_pattern(patterns_amount=old_patterns_amount,
                                                                 patterns_dir=path)
        self._renumber_patterns_faces_data_and_files(patterns_amount=patterns_amount,
                                                     patterns_dir=path)
        self._recalculate_patterns_centers(old_patterns_amount)
        self._register_verified_patterns_to_redis(old_patterns_amount)
        self._set_correct_status()
        self._another_album_processed = Faces.objects.filter(
            photo__album__owner__username_slug=self.object.owner.username_slug,
        ).exclude(photo__album__pk=self.object.pk).exists()
        if not self.formset.has_changed() and old_patterns_amount == 1:
            next_stage = 6 if self._another_album_processed else 9
            self._start_celery_task(next_stage)
        return super().form_valid(form)

    def _start_celery_task(self, next_stage):
        redis_instance.hset(f"album_{self.object.pk}", "current_stage", next_stage)
        redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
        redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        recognition_task.delay(self.object.pk, next_stage)

    def get_success_url(self):
        if self.formset.has_changed():
            return reverse_lazy('verify_patterns', kwargs={'album_slug': self.object.slug})
        else:
            if redis_instance.hget(f"album_{self.object.pk}", "number_of_verified_patterns") == '1':
                if self._another_album_processed:
                    return reverse_lazy('people_waiting', kwargs={'album_slug': self.object.slug})
                else:
                    return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})
            else:
                return reverse_lazy('group_patterns', kwargs={'album_slug': self.object.slug})

    def _replace_odd_faces_to_new_pattern(self, patterns_amount, patterns_dir):
        for i, cleaned_data in enumerate(self.formset.cleaned_data, 1):
            # Removing odd faces from existing pattern to new
            faces_to_remove = []
            for face_name, to_remove in cleaned_data.items():
                if to_remove:
                    faces_to_remove.append(face_name)

            if faces_to_remove:
                patterns_amount += 1
                faces_amount = redis_instance.hget(f"album_{self.object.pk}_pattern_{i}", "faces_amount")
                redis_instance.hset(f"album_{self.object.pk}_pattern_{patterns_amount}",
                                    "faces_amount", faces_amount)
                for k, face_name in enumerate(faces_to_remove):
                    # Moving face's data in redis
                    face_data = redis_instance.hget(f"album_{self.object.pk}_pattern_{i}", face_name)
                    redis_instance.hset(f"album_{self.object.pk}_pattern_{patterns_amount}",
                                        face_name,
                                        face_data)
                    redis_instance.expire(f"album_{self.object.pk}_pattern_{patterns_amount}",
                                          REDIS_DATA_EXPIRATION_SECONDS)
                    redis_instance.hdel(f"album_{self.object.pk}_pattern_{i}", face_name)

                    # Moving face image in temp directory
                    if k == 0:
                        os.makedirs(os.path.join(patterns_dir, str(patterns_amount)))
                    old_path = os.path.join(patterns_dir, str(i), f"{face_name[5:]}.jpg")
                    new_path = os.path.join(patterns_dir, str(patterns_amount), f"{face_name[5:]}.jpg")
                    os.replace(old_path, new_path)

        return patterns_amount

    def _renumber_patterns_faces_data_and_files(self, patterns_amount, patterns_dir):
        for i in range(1, patterns_amount + 1):
            faces_amount = int(redis_instance.hget(f"album_{self.object.pk}_pattern_{i}", "faces_amount"))
            count = 0
            for j in range(1, faces_amount + 1):
                if redis_instance.hexists(f"album_{self.object.pk}_pattern_{i}", f"face_{j}"):
                    count += 1
                    if count != j:
                        # Renumbering data keys in redis
                        redis_instance.hset(f"album_{self.object.pk}_pattern_{i}",
                                            f"face_{count}",
                                            redis_instance.hget(f"album_{self.object.pk}_pattern_{i}",
                                                                f"face_{j}"))
                        redis_instance.hdel(f"album_{self.object.pk}_pattern_{i}", f"face_{j}")

                        # Renumbering file
                        old_path = os.path.join(patterns_dir, str(i), f"{j}.jpg")
                        new_path = os.path.join(patterns_dir, str(i), f"{count}.jpg")
                        os.replace(old_path, new_path)

            redis_instance.hset(f"album_{self.object.pk}_pattern_{i}", "faces_amount", count)
            redis_instance.expire(f"album_{self.object.pk}_pattern_{i}", REDIS_DATA_EXPIRATION_SECONDS)

    def _recalculate_patterns_centers(self, verified_patterns_amount):
        for i in range(1, verified_patterns_amount + 1):
            # If pattern was not verified previously, but did now;
            # and it is not have one face (form wouldn't add fields)
            if self.formset.forms[i-1].fields:
                # Get PatterData from redis
                for k in range(1, int(redis_instance.hget(f"album_{self.object.pk}_pattern_{i}",
                                                          "faces_amount")) + 1):
                    face_address = redis_instance.hget(f"album_{self.object.pk}_pattern_{i}", f"face_{k}")
                    photo_pk, face_ind = re.search(r'photo_(\d+)_face_(\d+)', face_address).groups()
                    face_loc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_location"))
                    face_enc = pickle.loads(redis_instance_raw.hget(f"photo_{photo_pk}", f"face_{face_ind}_encoding"))
                    face = FaceData(photo_pk=int(photo_pk),
                                    index=int(face_ind),
                                    location=face_loc,
                                    encoding=face_enc)
                    if k == 1:
                        pattern = PatternData(face)
                    else:
                        pattern.add_face(face)

                # Set central face to redis
                pattern.find_central_face()
                for j, face in enumerate(pattern, 1):
                    if face is pattern.central_face:
                        redis_instance.hset(f"album_{self.object.pk}_pattern_{i}", "central_face", f"face_{j}")
                        break

    def _set_single_face_is_central(self):
        for i in range(self._number_of_verified_patterns + 1, len(self._faces_amounts) + 1):
            redis_instance.hset(f"album_{self.object.pk}_pattern_{i}", "central_face", f"face_1")

    def _register_verified_patterns_to_redis(self, verified_patterns_amount):
        redis_instance.hset(f"album_{self.object.pk}", "number_of_verified_patterns", verified_patterns_amount)

    def _set_correct_status(self, all_patterns_have_single_faces=False):
        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == self.recognition_stage - 1:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == self.recognition_stage and \
                (all_patterns_have_single_faces or not self.formset.has_changed()):
            redis_instance.hset(f"album_{self.object.pk}", "status", "completed")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)


class AlbumGroupPatternsView(LoginRequiredMixin, FormMixin, DetailView):
    recognition_stage = 5
    template_name = 'recognition/group_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = GroupPatternsForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == self.recognition_stage - 1 and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == self.recognition_stage and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - verifying patterns',
            'heading': "Group patterns of people.",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': ["Please mark faces belonging to the one same person."],
            'button_label': "Confirm",
        })

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self._get_single_patterns()
        kwargs.update({'single_patterns': self._single_patterns,
                       'album_pk': self.object.pk})
        return kwargs

    def _get_single_patterns(self):
        single_patterns = []
        for x in range(1, int(redis_instance.hget(f"album_{self.object.pk}", "number_of_verified_patterns")) + 1):
            if not redis_instance.hexists(f"album_{self.object.pk}_pattern_{x}", "person"):
                single_patterns.append(x)
        self._single_patterns = tuple(single_patterns)

    def form_valid(self, form):
        self._group_patterns_into_people(form)
        self._get_single_patterns()
        if not self._single_patterns:
            self._another_album_processed = Faces.objects.filter(
                photo__album__owner__username_slug=self.object.owner.username_slug,
            ).exclude(photo__album__pk=self.object.pk).exists()
            next_stage = 6 if self._another_album_processed else 9
            self._start_celery_task(next_stage)

        self._set_correct_status(form)
        return super().form_valid(form)

    def _group_patterns_into_people(self, form):
        if any(form.cleaned_data.values()):
            redis_instance.hincrby(f"album_{self.object.pk}", "people_amount")
            new_person_number = redis_instance.hget(f"album_{self.object.pk}", "people_amount")
            count = 0
            for field_name, to_group in form.cleaned_data.items():
                if to_group:
                    count += 1
                    redis_instance.hset(f"album_{self.object.pk}_{field_name}", "person", new_person_number)
                    redis_instance.expire(f"album_{self.object.pk}_{field_name}", REDIS_DATA_EXPIRATION_SECONDS)
                    redis_instance.hset(f"album_{self.object.pk}_person_{new_person_number}",
                                        f"pattern_{count}", field_name[8:])
            redis_instance.expire(f"album_{self.object.pk}_person_{new_person_number}", REDIS_DATA_EXPIRATION_SECONDS)

        else:
            for field_name in form.cleaned_data.keys():
                redis_instance.hincrby(f"album_{self.object.pk}", "people_amount")
                new_person_number = redis_instance.hget(f"album_{self.object.pk}", "people_amount")

                redis_instance.hset(f"album_{self.object.pk}_{field_name}", "person", new_person_number)
                redis_instance.expire(f"album_{self.object.pk}_{field_name}", REDIS_DATA_EXPIRATION_SECONDS)
                redis_instance.hset(f"album_{self.object.pk}_person_{new_person_number}",
                                    f"pattern_1", field_name[8:])
                redis_instance.expire(f"album_{self.object.pk}_person_{new_person_number}",
                                      REDIS_DATA_EXPIRATION_SECONDS)

    def _set_correct_status(self, form):
        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == self.recognition_stage - 1:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == self.recognition_stage and \
                not any(form.cleaned_data.values()):
            if self._another_album_processed:
                redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage + 1)
            else:
                redis_instance.hset(f"album_{self.object.pk}", "current_stage",
                                    AlbumRecognitionDataSavingWaitingView.recognition_stage)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _start_celery_task(self, next_stage):
        redis_instance.hset(f"album_{self.object.pk}", "current_stage", next_stage)
        redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
        redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        recognition_task.delay(self.object.pk, next_stage)

    def get_success_url(self):
        if self._single_patterns:
            return reverse_lazy('group_patterns', kwargs={'album_slug': self.object.slug})
        else:
            if self._another_album_processed:
                return reverse_lazy('people_waiting', kwargs={'album_slug': self.object.slug})
            else:
                return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})


class ComparingAlbumPeopleWaitingView(LoginRequiredMixin, DetailView):
    recognition_stage = 6
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_people.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self.status = redis_instance.hget(f"album_{self.object.pk}", "status")
        self._check_any_tech_matches()
        if self.status == 'completed' and not self._any_tech_matches:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage + 1)

        return super().get(request, *args, **kwargs)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if current_stage != self.recognition_stage:
            raise Http404

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            instructions = [
                "Now the people found in the photos of this album are searched in your other processed albums.",
                "This should take no more than a moment.",
                "Please refresh the page.",
            ]
            button_label = 'waiting'
            next = None

        else:
            title = f'Album \"{self.object}\" - ready to continue'
            is_ready = True
            if self._any_tech_matches:
                instructions = [
                    "Some matches are found.",
                    "Please check them.",
                ]
                button_label = 'Check matches'
                next = 'verify_matches'
            else:
                instructions = [
                    "We didn't found any matches.",
                    "Please continue.",
                ]
                button_label = 'Continue'
                next = 'manual_matching'

        context.update({
            'title': title,
            'is_ready': is_ready,
            'heading': "Looking for people matches in your other processed albums",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': instructions,
            'button_label': button_label,
            'next': next,
        })

        return context

    def _check_any_tech_matches(self):
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hget(f"album_{self.object.pk}_person_{i}", "tech_pair"):
                self._any_tech_matches = True
                break
            i += 1
        else:
            self._any_tech_matches = False


class VerifyTechPeopleMatchesView(LoginRequiredMixin, FormMixin, DetailView):
    recognition_stage = 7
    template_name = 'recognition/verify_matches.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = VarifyMatchesForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self._get_matches_urls()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self._get_matches_urls()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == self.recognition_stage - 1 and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == self.recognition_stage and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'match_imgs_urls': self._matches_urls,
        })
        return kwargs

    def _get_matches_urls(self):
        # Getting index of new person and pk of old person in matches
        old_people_pks = []
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "tech_pair"):
                pk = int(redis_instance.hget(f"album_{self.object.pk}_person_{i}", "tech_pair")[7:])
                old_people_pks.append(pk)
                new_people_inds.append(i)
            i += 1

        # Getting urls of first faces of first patterns of each person
        # new people
        patt_inds = [redis_instance.hget(f"album_{self.object.pk}_person_{x}", "pattern_1") for x in new_people_inds]
        face_urls = [f"/media/temp_photos/album_{self.object.pk}/patterns/{x}/1.jpg" for x in patt_inds]

        # old people
        old_face_urls = [reverse('get_face_img', kwargs={
            'face_slug': People.objects.get(pk=x).patterns_set.all()[0].faces_set.all()[0].slug,
        }) for x in old_people_pks]

        self._matches_urls = tuple(zip(new_people_inds, old_people_pks, face_urls, old_face_urls))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        new_ppl_urls = {}
        old_ppl_urls = {}
        for new_people_ind, old_people_pk, face_url, old_face_url in self._matches_urls:
            new_ppl_urls.update({f"new{new_people_ind}_old{old_people_pk}": face_url})
            old_ppl_urls.update({f"new{new_people_ind}_old{old_people_pk}": old_face_url})

        context.update({
            'title': f'Album \"{self.object}\" - verifying matches',
            'heading': "Verify automatic matching.",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': ["Please mark pairs, that are depicting DIFFERENT people."],
            'button_label': "Confirm",
            'new_ppl_urls': new_ppl_urls,
            'old_ppl_urls': old_ppl_urls,
        })

        return context

    def form_valid(self, form):
        self._register_verified_matches_to_redis(form=form)
        self._check_new_single_people()
        self._check_old_single_people()
        if not self._new_singe_people_present or not self._old_singe_people_present:
            recognition_task.delay(self.object.pk, AlbumRecognitionDataSavingWaitingView.recognition_stage)
        self._set_correct_status()
        return super().form_valid(form)

    def _register_verified_matches_to_redis(self, form):
        for pair, to_delete in form.cleaned_data.items():
            if not to_delete:
                _, new_per_ind, old_per_pk = pair.split('_')
                redis_instance.hset(f"album_{self.object.pk}_person_{new_per_ind}", "real_pair", f"person_{old_per_pk}")

    def _set_correct_status(self):
        if not self._new_singe_people_present or not self._old_singe_people_present:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", 9)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
        else:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", 7)
            redis_instance.hset(f"album_{self.object.pk}", "status", "completed")
        redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _check_new_single_people(self):
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                self._new_singe_people_present = True
                break
            i += 1
        else:
            self._new_singe_people_present = False

    def _check_old_single_people(self):
        queryset = People.objects.filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{self.object.pk}_person_{i}", "real_pair")[7:]))
            i += 1

        # Iterating through people, filtering already paired
        for person in queryset:
            if person.pk not in paired:
                self._old_singe_people_present = True
                break
        else:
            self._old_singe_people_present = False

    def get_success_url(self):
        if self._new_singe_people_present and self._old_singe_people_present:
            return reverse_lazy('manual_matching', kwargs={'album_slug': self.object.slug})
        else:
            return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})


class ManualMatchingPeopleView(LoginRequiredMixin, FormMixin, DetailView):
    recognition_stage = 8
    template_name = 'recognition/manual_matching.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = ManualMatchingForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == self.recognition_stage - 1 and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == self.recognition_stage and
                redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'new_ppl': self._get_new_ppl(),
            'old_ppl': self._get_old_ppl(),
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - manual matching',
            'heading': "Manually matching same person faces.",
            'current_stage': self.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'instructions': ["Please mark pair of faces that belongs to same person.",
                             "If there is no matching faces - check the box \"Here is no"
                             " matches\", and press \"Confirm\""],
            'button_label': "Confirm",
        })

        return context

    def _get_new_ppl(self):
        new_people_inds = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                new_people_inds.append(i)
            i += 1

        patt_inds = [redis_instance.hget(f"album_{self.object.pk}_person_{x}", "pattern_1") for x in new_people_inds]
        face_urls = [f"/media/temp_photos/album_{self.object.pk}/patterns/{x}/1.jpg" for x in patt_inds]

        return tuple(zip(new_people_inds, face_urls))

    def _get_old_ppl(self):
        queryset = People.objects.prefetch_related('patterns_set__faces_set').filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{self.object.pk}_person_{i}", "real_pair")[7:]))
            i += 1

        # Taking face image url of one of the faces of person,
        # if it is not already paired with one of people from this album
        old_ppl = []
        for person in queryset:
            if person.pk not in paired:
                old_ppl.append((person.pk,
                                reverse('get_face_img',
                                        kwargs={'face_slug': person.patterns_set.all()[0].faces_set.all()[0].slug})))

        return old_ppl

    def form_valid(self, form):
        self._done = form.cleaned_data.get('done', False)

        if not self._done and not form.cleaned_data.get('new_ppl') and not form.cleaned_data.get('new_ppl'):
            self._done = True

        if not self._done:
            self._register_new_pair_to_redis(form=form)
            self._check_another_pairing_possible()

        self._set_correct_status()

        if self._done:
            recognition_task.delay(self.object.pk, AlbumRecognitionDataSavingWaitingView.recognition_stage)

        return super().form_valid(form)

    def _register_new_pair_to_redis(self, form):
        new_person_ind = form.cleaned_data.get('new_person')
        old_person_pk = form.cleaned_data.get('old_person')

        redis_instance.hset(f'album_{self.object.pk}_person_{new_person_ind}',
                            'real_pair',
                            f'person_{old_person_pk}')
        redis_instance.expire(f'album_{self.object.pk}_person_{new_person_ind}', REDIS_DATA_EXPIRATION_SECONDS)

    def _check_another_pairing_possible(self):
        self._check_new_single_people()
        self._check_old_single_people()
        if not self._new_singe_people_present or not self._old_singe_people_present:
            self._done = True

    def _check_new_single_people(self):
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if not redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                self._new_singe_people_present = True
                break
            i += 1
        else:
            self._new_singe_people_present = False

    def _check_old_single_people(self):
        queryset = People.objects.filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = []
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hexists(f"album_{self.object.pk}_person_{i}", "real_pair"):
                paired.append(int(redis_instance.hget(f"album_{self.object.pk}_person_{i}", "real_pair")[7:]))
            i += 1

        # Iterating through people, filtering already paired
        for person in queryset:
            if person.pk not in paired:
                self._old_singe_people_present = True
                break
        else:
            self._old_singe_people_present = False

    def get_success_url(self):
        if self._done:
            return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})
        else:
            return reverse_lazy('manual_matching', kwargs={'album_slug': self.object.slug})

    def _set_correct_status(self):
        if self._done:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage + 1)

        else:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", self.recognition_stage)
        redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
        redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def _are_any_tech_matches(self):
        i = 1
        while redis_instance.exists(f"album_{self.object.pk}_person_{i}"):
            if redis_instance.hget(f"album_{self.object.pk}_person_{i}", "tech_pair"):
                return True
            i += 1
        else:
            return False


class AlbumRecognitionDataSavingWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 9
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/base/waiting_base.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_recognition_stage()

        self._set_status()

        return super().get(request, *args, **kwargs)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_recognition_stage(self):
        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            if redis_instance.get(f"album_{self.object.pk}_finished") != '1':
                raise Http404
        else:
            if current_stage != self.recognition_stage:
                raise Http404

    def _set_status(self):
        if redis_instance.hexists(f"album_{self.object.pk}", "current_stage"):
            self.status = redis_instance.hget(f"album_{self.object.pk}", "status")
        else:
            self.status = 'completed'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            instructions = [
                "Saving recognised people data to Data Base",
                "Once this is completed, you can search for people in other users' photos and they in yours."
                "This should take no more than a moment.",
                "Please refresh the page.",
            ]
            button_label = 'waiting'
            next = None

        else:
            title = f'Album \"{self.object}\" - recognition done'
            is_ready = True
            instructions = [
                "Data is successfully saved.",
                "Now you can search for people in your photos in other users' photos!",
            ]
            button_label = 'To recognised people'
            next = 'recognition_main'

        context.update({
            'title': title,
            'is_ready': is_ready,
            'heading': "Saving all data to Data Base",
            'current_stage': self.recognition_stage,
            'total_stages': self.recognition_stage,
            'instructions': instructions,
            'button_label': button_label,
            'next': next,
        })

        return context


class NoFacesAlbumView(LoginRequiredMixin, RecognitionMixin, DetailView):
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/base/waiting_base.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        self._check_access_right()
        self._check_photos_processed_and_no_faces_found()

        set_album_photos_processed(album_pk=self.object.pk, status=True)

        return super().get(request, *args, **kwargs)

    def _check_access_right(self):
        if self.request.user.username_slug != self.object.owner.username_slug:
            raise Http404

    def _check_photos_processed_and_no_faces_found(self):
        if not redis_instance.get(f"album_{self.object.pk}_finished") == "no_faces":
            raise Http404

        if self._photos_processed_and_any_faces_found():
            raise Http404

    def _photos_processed_and_any_faces_found(self):
        pks = tuple(map(lambda p: p.pk, self.object.photos_set.all()))
        for pk in pks:
            if not redis_instance.exists(f"photo_{pk}"):
                return False

        for pk in pks:
            if redis_instance.hexists(f"photo_{pk}", "face_1_location"):
                return True

        return False

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        instructions = [f"Sorry, we couldn't find any faces in {self.object.title} album."]
        title = f'Album \"{self.object}\" - no faces found'

        context.update({
            'is_ready': True,
            'current_stage': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'total_stages': AlbumRecognitionDataSavingWaitingView.recognition_stage,
            'heading': "No Faces founded",
            'instructions': instructions,
            'title': title,
            'button_label': "To albums recognition",
            'next': 'recognition_main',
        })

        return context
