import os

from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy, reverse
from django.views.decorators.csrf import csrf_protect
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Prefetch
from django.views.generic.edit import FormMixin, FormView

from PIL import Image, ImageDraw, ImageFont

from mainapp.models import Photos, Albums
from .forms import *
from .models import Faces, People, Patterns
from .supporters import RedisSupporter
from .tasks import recognition_task
from photoalbums.settings import MEDIA_ROOT, BASE_DIR
from .utils import set_album_photos_processed
from .mixin_views import RecognitionMixin


@login_required
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


@login_required
def return_photo_with_framed_faces(request, photo_slug):
    photo = Photos.objects.select_related('album__owner').get(slug=photo_slug)

    if not request.user.is_authenticated or request.user.pk != photo.album.owner.pk or photo.is_private:
        raise Http404

    # Loading faces locations from redis
    faces_locations = RedisSupporter.get_face_locations_in_photo(photo.pk)

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
                     'heading': 'Process your albums for recognition'}
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

    RedisSupporter.set_stage_and_status(album_pk=album.pk, stage=0, status="processing")
    recognition_task.delay(album.pk, 1)

    return redirect('frames_waiting', album_slug=album_slug)


class AlbumFramesWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 1
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_frames.html'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        if self._photos_processed_and_no_faces_found():
            RedisSupporter.set_no_faces(album_pk=self.object.pk)
            recognition_task.delay(self.object.pk, -1)
            return redirect('no_faces', album_slug=self.object.slug)

        return super().get(request, *args, **kwargs)

    def _check_recognition_stage(self, waiting_task=True):
        current_stage = RedisSupporter.get_stage_or_404(self.object.pk)
        if current_stage not in (self.recognition_stage - 1, self.recognition_stage):
            raise Http404

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        number_of_processed_photos = RedisSupporter.get_processed_photos_amount(self.object.pk)
        status = RedisSupporter.get_status(self.object.pk)

        if status == "processing":
            progress = 10
            is_ready = False
            instructions = [
                "We are searching for faces on photos of this album.",
                " This may take a minute or two.",
                "Please refresh this page until you see that all the photos have been processed.",
            ]
            title = f'Album \"{self.object}\" - waiting'
        else:
            progress = 20
            is_ready = True
            instructions = [
                "We are ready to continue. You can press the button!",
            ]
            title = f'Album \"{self.object}\" - ready to continue'

        first_photo_slug = RedisSupporter.get_first_photo_slug(self.object.pk)

        context.update({
            'heading': "Searching for faces on album's photos",
            'progress': progress,
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
        return all(map(RedisSupporter.photo_processed_and_no_faces_found, pks))

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
        self._get_object_and_make_checks(queryset=self.model.objects.filter(album_id=self.album.pk))

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.album = Albums.objects.select_related('owner').prefetch_related('photos_set').get(slug=kwargs['album_slug'])
        self._get_object_and_make_checks(queryset=self.model.objects.filter(album_id=self.album.pk))


        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_access_right(self):
        if self.request.user.username_slug != self.album.owner.username_slug or self.object.is_private:
            raise Http404

    def _check_recognition_stage(self, waiting_task=False):
        stage = RedisSupporter.get_stage_or_404(self.album.pk)
        status = RedisSupporter.get_status(self.album.pk)
        if not (stage == self.recognition_stage and status == "processing" or
                stage == self.recognition_stage - 1 and status == "completed"):
            raise Http404

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'faces_amount': RedisSupporter.get_faces_amount_in_photo(self.object.pk)})
        return kwargs

    def form_valid(self, form):
        self._delete_wrong_data(form)
        RedisSupporter.renumber_faces_of_photo(self.object.pk)
        self._set_correct_status()

        self._is_last_photo = self.object.slug == RedisSupporter.get_last_photo_slug(self.album.pk)
        if self._is_last_photo:
            self._count_verified_faces()
            if self._faces_amount == 0:
                RedisSupporter.set_no_faces(self.album.pk)
                recognition_task.delay(self.album.pk, -1)
            else:
                self._get_next_stage()
                self._start_celery_task(self._next_stage)

        return super().form_valid(form)

    def _delete_wrong_data(self, form):
        for name, to_delete in form.cleaned_data.items():
            if to_delete:
                RedisSupporter.del_face(self.object.pk, name)

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
        RedisSupporter.register_photo_processed(self.album.pk)

        if RedisSupporter.get_stage(self.album.pk) == self.recognition_stage - 1 and \
                self.object.slug == RedisSupporter.get_first_photo_slug(self.album.pk):
            RedisSupporter.set_stage_and_status(album_pk=self.album.pk,
                                                stage=self.recognition_stage, status="processing")
        if RedisSupporter.get_stage(self.album.pk) == self.recognition_stage and \
                self.object.slug == RedisSupporter.get_last_photo_slug(self.album.pk):
            RedisSupporter.set_stage_and_status(album_pk=self.album.pk,
                                                stage=self.recognition_stage, status="completed")
            RedisSupporter.reset_processed_photos_amount(self.album.pk)

    def get_success_url(self):
        if self._is_last_photo:
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
            next_photo_slug = RedisSupporter.get_next_photo_slug(album_pk=self.album.pk,
                                                                 current_photo_slug=self.object.slug)
            return reverse_lazy('verify_frames', kwargs={'album_slug': self.album.slug, 'photo_slug': next_photo_slug})

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        current_photo_number = RedisSupporter.get_processed_photos_amount(self.album.pk) + 1
        photos_with_faces = RedisSupporter.get_photo_slugs_amount(self.album.pk)
        instructions = ["Please mark the faces of children under 10 and objects that are not faces."]
        if self.object.slug == RedisSupporter.get_last_photo_slug(self.album.pk):
            button_label = "Next stage"
        else:
            button_label = "Next photo"

        context.update({
            'title': f'Album \"{self.album}\" - verifying frames',
            'heading': f"Verifying photo {self.object.title} ({current_photo_number}/{photos_with_faces})",
            'instructions': instructions,
            'progress': 20 + 10 * current_photo_number // photos_with_faces,
            'button_label': button_label,
        })

        return context

    def _start_celery_task(self, next_stage):
        RedisSupporter.set_stage_and_status(album_pk=self.album.pk, stage=next_stage, status="processing")
        recognition_task.delay(self.album.pk, next_stage)

    def _count_verified_faces(self):
        count = 0
        for pk in map(lambda p: p.pk, self.album.photos_set.all()):
            if RedisSupporter.is_face_in_photo(photo_pk=pk, face_index=1):
                count += 1
        self._faces_amount = count


class AlbumPatternsWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 3
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_patterns.html'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks(waiting_task=True)
        self.status = RedisSupporter.get_status(self.object.pk)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            progress = 30
            instructions = [
                "Now verified faces are combined into patterns.",
                "This should take no more than a moment.",
                "Please refresh this page now.",
            ]

        else:
            title = f'Album \"{self.object}\" - ready to continue'
            is_ready = True
            progress = 40
            instructions = ["Patterns of faces has created, we are ready to continue."]

        context.update({
            'title': title,
            'is_ready': is_ready,
            'progress': progress,
            'heading': "Recognizing faces. Creating patterns.",
            'instructions': instructions,
            'button_label': "Verify results",
            'next': 'verify_patterns',
        })

        return context


class AlbumVerifyPatternsView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    recognition_stage = 4
    template_name = 'recognition/verify_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = BaseVerifyPatternForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        self._faces_amounts = RedisSupporter.get_album_faces_amounts(self.object.pk)
        self._verified_patterns_amount = RedisSupporter.get_verified_patterns_amount(self.object.pk)

        # If all patterns have only one face each
        if all(map(lambda x: x == 1, self._faces_amounts[self._verified_patterns_amount:])):
            self._prepare_to_redirect_to_next_stage()
            return redirect('group_patterns', album_slug=self.object.slug)

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._verified_patterns_amount,
                                            album_pk=self.object.pk)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        self._faces_amounts = RedisSupporter.get_album_faces_amounts(self.object.pk)
        self._verified_patterns_amount = RedisSupporter.get_verified_patterns_amount(self.object.pk)

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(request.POST, faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._verified_patterns_amount,
                                            album_pk=self.object.pk)

        form = self.get_form()
        if self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _prepare_to_redirect_to_next_stage(self):
        RedisSupporter.register_verified_patterns(self.object.pk, len(self._faces_amounts))
        RedisSupporter.set_single_face_central(album_pk=self.object.pk, total_patterns_amount=len(self._faces_amounts),
                                               skip=self._verified_patterns_amount)
        self._set_correct_status(all_patterns_have_single_faces=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - verifying patterns',
            'formset': self.formset,
            'heading': "Verifying patterns of people's faces.",
            'progress': 40,
            'instructions': [
                "In each row, there should be faces belonging to one person.",
                "Please mark mismatched ones.",
            ],
            'button_label': "Confirm",
        })

        return context

    def form_valid(self, form):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self.object.pk}/patterns')
        old_patterns_amount = len(self._faces_amounts)
        patterns_amount = self._replace_odd_faces_to_new_pattern(patterns_amount=old_patterns_amount,
                                                                 patterns_dir=path)
        self._renumber_patterns_faces_data_and_files(patterns_amount=patterns_amount,
                                                     patterns_dir=path)
        self._recalculate_patterns_centers(old_patterns_amount)
        RedisSupporter.register_verified_patterns(self.object.pk, old_patterns_amount)
        self._set_correct_status()
        self._another_album_processed = Faces.objects.filter(
            photo__album__owner__username_slug=self.object.owner.username_slug,
        ).exclude(photo__album__pk=self.object.pk).exists()
        if not self.formset.has_changed() and old_patterns_amount == 1:
            next_stage = 6 if self._another_album_processed else 9
            self._start_celery_task(next_stage)
        return super().form_valid(form)

    def _start_celery_task(self, next_stage):
        RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=next_stage, status="processing")
        recognition_task.delay(self.object.pk, next_stage)

    def get_success_url(self):
        if self.formset.has_changed():
            return reverse_lazy('verify_patterns', kwargs={'album_slug': self.object.slug})
        else:
            if RedisSupporter.get_verified_patterns_amount(self.object.pk) == 1:
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
                faces_amount = RedisSupporter.get_pattern_faces_amount(self.object.pk, i)
                RedisSupporter.set_pattern_faces_amount(album_pk=self.object.pk, pattern_index=patterns_amount,
                                                        faces_amount=faces_amount)
                for k, face_name in enumerate(faces_to_remove):
                    # Moving face's data in redis
                    RedisSupporter.move_face_data(album_pk=self.object.pk, face_name=face_name,
                                                  from_pattern=i, to_pattern=patterns_amount)

                    # Moving face image in temp directory
                    if k == 0:
                        os.makedirs(os.path.join(patterns_dir, str(patterns_amount)))
                    old_path = os.path.join(patterns_dir, str(i), f"{face_name[5:]}.jpg")
                    new_path = os.path.join(patterns_dir, str(patterns_amount), f"{face_name[5:]}.jpg")
                    os.replace(old_path, new_path)

        return patterns_amount

    def _renumber_patterns_faces_data_and_files(self, patterns_amount, patterns_dir):
        for i in range(1, patterns_amount + 1):
            faces_amount = RedisSupporter.get_pattern_faces_amount(self.object.pk, i)

            # Renumbering files
            count = 0
            for j in range(1, faces_amount + 1):
                if RedisSupporter.is_face_in_pattern(self.object.pk, face_index=j, pattern_index=i):
                    count += 1
                    if count != j:
                        old_path = os.path.join(patterns_dir, str(i), f"{j}.jpg")
                        new_path = os.path.join(patterns_dir, str(i), f"{count}.jpg")
                        os.replace(old_path, new_path)

            # Renumbering redis data
            RedisSupporter.renumber_faces_in_patterns(album_pk=self.object.pk, pattern_index=i,
                                                      faces_amount=faces_amount)

    def _recalculate_patterns_centers(self, verified_patterns_amount):
        for i in range(1, verified_patterns_amount + 1):
            # If pattern was not verified previously, but did now;
            # and it is not have one face (form wouldn't add fields)
            if self.formset.forms[i-1].fields:
                RedisSupporter.recalculate_pattern_center(self.object.pk, i)

    def _set_correct_status(self, all_patterns_have_single_faces=False):
        if RedisSupporter.get_stage(self.object.pk) == self.recognition_stage - 1:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=self.recognition_stage,
                                                status="processing")

        if RedisSupporter.get_stage(self.object.pk) == self.recognition_stage and \
                (all_patterns_have_single_faces or not self.formset.has_changed()):
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=self.recognition_stage,
                                                status="completed")


class AlbumGroupPatternsView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    recognition_stage = 5
    template_name = 'recognition/group_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = GroupPatternsForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - verifying patterns',
            'heading': "Group patterns of people.",
            'progress': 50,
            'instructions': [
                "Please mark all faces belonging to the one same person.",
                "If these are all faces of different people, do not mark any.",
            ],
            'button_label': "Confirm",
        })

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self._single_patterns = RedisSupporter.get_indexes_of_single_patterns(self.object.pk)
        kwargs.update({'single_patterns': self._single_patterns,
                       'album_pk': self.object.pk})
        return kwargs

    def form_valid(self, form):
        self._group_patterns_into_people(form)
        self._single_patterns = RedisSupporter.get_indexes_of_single_patterns(self.object.pk)
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
            new_person_number = RedisSupporter.encrease_and_get_people_amount(self.object.pk)
            count = 0
            for field_name, to_group in form.cleaned_data.items():
                if to_group:
                    count += 1
                    RedisSupporter.set_pattern_to_person(album_pk=self.object.pk,
                                                         pattern_name=field_name,
                                                         pattern_number_in_person=count,
                                                         person_number=new_person_number)
        else:
            for field_name in form.cleaned_data.keys():
                RedisSupporter.set_created_person(album_pk=self.object.pk, pattern_name=field_name)

    def _set_correct_status(self, form):
        if RedisSupporter.get_stage(self.object.pk) == self.recognition_stage - 1:
            RedisSupporter.set_stage_and_status(self.object.pk, stage=self.recognition_stage, status="processing")

        if RedisSupporter.get_stage(self.object.pk) == self.recognition_stage and \
                not any(form.cleaned_data.values()):
            if self._another_album_processed:
                RedisSupporter.set_stage_and_status(self.object.pk, stage=self.recognition_stage+1, status="processing")
            else:
                RedisSupporter.set_stage_and_status(self.object.pk, stage=9, status="processing")

    def _start_celery_task(self, next_stage):
        RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=next_stage, status="processing")
        recognition_task.delay(self.object.pk, next_stage)

    def get_success_url(self):
        if self._single_patterns:
            return reverse_lazy('group_patterns', kwargs={'album_slug': self.object.slug})
        else:
            if self._another_album_processed:
                return reverse_lazy('people_waiting', kwargs={'album_slug': self.object.slug})
            else:
                return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})


class ComparingAlbumPeopleWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 6
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/waiting_people.html'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks(waiting_task=True)

        self.status = RedisSupporter.get_status(self.object.pk)
        self._any_tech_matches = RedisSupporter.check_any_tech_matches(self.object.pk)
        if self.status == 'completed' and not self._any_tech_matches:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=self.recognition_stage+1,
                                                status='completed')

        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            progress = 60
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
            progress = 70
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
            'progress': progress,
            'instructions': instructions,
            'button_label': button_label,
            'next': next,
        })

        return context


class VerifyTechPeopleMatchesView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    recognition_stage = 7
    template_name = 'recognition/verify_matches.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = VarifyMatchesForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        self._get_matches_urls()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        self._get_matches_urls()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'match_imgs_urls': self._matches_urls,
        })
        return kwargs

    def _get_matches_urls(self):
        # Getting index of new person and pk of old person in matches
        old_people_pks, new_people_inds = RedisSupporter.get_matching_people(self.object.pk)

        # Getting urls of first faces of first patterns of each person
        # new people
        patt_inds = RedisSupporter.get_first_patterns_indexes_of_people(self.object.pk, new_people_inds)
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
            'progress': 70,
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
                RedisSupporter.set_verified_pair(self.object.pk, new_per_ind, old_per_pk)

    def _set_correct_status(self):
        if not self._new_singe_people_present or not self._old_singe_people_present:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=9, status="processing")
        else:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=7, status="completed")

    def _check_new_single_people(self):
        self._new_singe_people_present = RedisSupporter.check_existing_new_single_people(album_pk=self.object.pk)

    def _check_old_single_people(self):
        queryset = People.objects.filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = RedisSupporter.get_old_paired_people(self.object.pk)

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


class ManualMatchingPeopleView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    recognition_stage = 8
    template_name = 'recognition/manual_matching.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = ManualMatchingForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'new_ppl': RedisSupporter.get_new_unpaired_people(self.object.pk),
            'old_ppl': self._get_old_ppl(),
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - manual matching',
            'heading': "Manually matching same person faces.",
            'progress': 80,
            'instructions': ["Please mark pair of faces that belongs to same person.",
                             "If there is no matching faces don't mark any.",
                             "Or check the box \"Here is no matches\", and press \"Confirm\""],
            'button_label': "Confirm",
        })

        return context

    def _get_old_ppl(self):
        queryset = People.objects.prefetch_related('patterns_set__faces_set').filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = RedisSupporter.get_old_paired_people(self.object.pk)

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
        RedisSupporter.set_new_pair(album_pk=self.object.pk, new_person_ind=new_person_ind, old_person_pk=old_person_pk)

    def _check_another_pairing_possible(self):
        self._new_singe_people_present = RedisSupporter.check_existing_new_single_people(self.object.pk)
        self._old_singe_people_present = self._check_old_single_people()
        if not self._new_singe_people_present or not self._old_singe_people_present:
            self._done = True

    def _check_old_single_people(self):
        queryset = People.objects.filter(owner__pk=self.object.owner.pk)

        # Collecting already paired people with created people of this album
        paired = RedisSupporter.get_old_paired_people(self.object.pk)

        # Iterating through people, filtering already paired
        for person in queryset:
            if person.pk not in paired:
                return True
        else:
            return False

    def get_success_url(self):
        if self._done:
            return reverse_lazy('save_waiting', kwargs={'album_slug': self.object.slug})
        else:
            return reverse_lazy('manual_matching', kwargs={'album_slug': self.object.slug})

    def _set_correct_status(self):
        if self._done:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=self.recognition_stage + 1,
                                                status="processing")
        else:
            RedisSupporter.set_stage_and_status(album_pk=self.object.pk, stage=self.recognition_stage,
                                                status="processing")


class AlbumRecognitionDataSavingWaitingView(LoginRequiredMixin, RecognitionMixin, DetailView):
    recognition_stage = 9
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/base/waiting_base.html'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks(waiting_task=True)

        self._status = RedisSupporter.get_status_or_completed(self.object.pk)
        if self._status == 'completed':
            return redirect('rename_people', album_slug=self.object.slug)

        return super().get(request, *args, **kwargs)

    def _check_recognition_stage(self, waiting_task=True):
        try:
            current_stage = RedisSupporter.get_stage(self.object.pk)
        except TypeError:
            if RedisSupporter.get_finished_status(self.object.pk) != '1':
                raise Http404
        else:
            if current_stage != self.recognition_stage:
                raise Http404

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        if self._status == "processing":
            title = f'Album \"{self.object}\" - waiting'
            is_ready = False
            progress = 90
            instructions = [
                "Saving recognised people data to Data Base",
                "Once this is completed, you can search for people in other users' photos and they in yours."
                "This may take a minute or two.",
                "Please refresh the page.",
            ]
            button_label = 'waiting'
            next = None

        else:
            title = f'Album \"{self.object}\" - recognition done'
            is_ready = True
            progress = 100
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
            'progress': progress,
            'instructions': instructions,
            'button_label': button_label,
            'next': next,
        })

        return context


class RenameAlbumsPeopleView(LoginRequiredMixin, FormMixin, RecognitionMixin, DetailView):
    template_name = 'recognition/rename_people.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        self.formset = self._get_formset()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_object_and_make_checks()

        form = self.get_form()
        self.formset = self._get_formset()
        if self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _check_recognition_stage(self, waiting_task):
        if RedisSupporter.get_stage(self.object.pk) or RedisSupporter.get_finished_status(self.object.pk) != '1':
            raise Http404

    def _get_formset(self):
        faces = Faces.objects.filter(photo__album__pk=self.object.pk).select_related('pattern__person')
        people_pks = set(map(lambda f: f.pattern.person.pk, faces))
        if self.request.method == 'GET':
            return RenamePeopleFormset(queryset=People.objects.filter(pk__in=people_pks))
        elif self.request.method == 'POST':
            return RenamePeopleFormset(self.request.POST, queryset=People.objects.filter(pk__in=people_pks))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        instructions = [
            "This is all people we found in album."
            "They will be saved under these names.",
            "You will NOT be able to rename them without repeating this procedure later.",
        ]
        title = f'Album \"{self.object}\" - naming people'

        context.update({
            'is_ready': True,
            'progress': 100,
            'heading': "Rename people, if you want",
            'instructions': instructions,
            'title': title,
            'button_label': "Finish recognition",
        })

        return context

    def form_valid(self, form):
        self.formset.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('recognition_main')


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

    def _check_photos_processed_and_no_faces_found(self):
        if RedisSupporter.get_finished_status(self.object.pk) != "no_faces":
            raise Http404

        if self._album_processed_and_some_faces_found():
            raise Http404

    def _album_processed_and_some_faces_found(self):
        pks = tuple(map(lambda p: p.pk, self.object.photos_set.all()))
        return any(map(RedisSupporter.photo_processed_and_some_faces_found, pks))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        instructions = [f"Sorry, we couldn't find any faces in {self.object.title} album."]
        title = f'Album \"{self.object}\" - no faces found'

        context.update({
            'is_ready': True,
            'progress': 100,
            'heading': "No Faces founded",
            'instructions': instructions,
            'title': title,
            'button_label': "To albums recognition",
            'next': 'recognition_main',
        })

        return context


class RecognizedPeopleView(LoginRequiredMixin, ListView):
    model = People
    template_name = 'recognition/people.html'
    context_object_name = 'people'
    extra_context = {'title': 'Recognition - Albums',
                     'current_section': 'recognition_main'}
    paginate_by = 24

    def get_queryset(self):
        queryset = self.model.objects.select_related(
            'owner',
        ).prefetch_related(
            'patterns_set__faces_set',
        ).filter(owner__pk=self.request.user.pk)
        return queryset


class RecognizedPersonView(LoginRequiredMixin, ListView):
    model = Patterns
    template_name = 'recognition/person.html'
    context_object_name = 'patterns'

    def get_queryset(self):
        queryset = self.model.objects.prefetch_related(
            Prefetch('faces_set',
                     queryset=Faces.objects.filter(
                         pattern__person__owner__pk=self.request.user.pk
                     ).select_related('photo__album'))
        ).filter(person__slug=self.kwargs['person_slug'])

        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self._get_person()

        context.update({
            'title': f'Recognition - person {person.name}',
            'person': person,
        })

        return context

    def _get_person(self):
        person = People.objects.annotate(
            photos_amount=Count('patterns__faces__photo', distinct=True),
            albums_amount=Count('patterns__faces__photo__album', distinct=True),
        ).get(slug=self.kwargs['person_slug'])
        return person


class SearchPeopleView(LoginRequiredMixin, ListView):
    pass
