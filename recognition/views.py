import os
import redis

from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_protect
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.views.generic.edit import FormMixin

from mainapp.models import *
from .forms import VerifyFramesForm, BaseVerifyPatternForm, BaseVerifyPatternFormset, GroupPatternsForm
from .tasks import face_searching_task, relate_faces_task
from photoalbums.settings import REDIS_HOST, REDIS_PORT, REDIS_DATA_EXPIRATION_SECONDS, MEDIA_ROOT

redis_instance = redis.Redis(host=REDIS_HOST,
                             port=REDIS_PORT,
                             db=0,
                             decode_responses=True)
redis_instance_raw = redis.Redis(host=REDIS_HOST,
                                 port=REDIS_PORT,
                                 db=0,
                                 decode_responses=False)


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

    def get_queryset(self):
        queryset = self.model.objects.filter(owner__pk=self.request.user.pk).annotate(
            public_photos=Count('photos', filter=Q(photos__is_private=False)),
            processed_photos=Count('photos', filter=(Q(photos__is_private=False) & Q(photos__faces_extracted=True)))
        )
        return queryset


@csrf_protect
@login_required
def find_faces_view(request, album_slug):
    if request.method != 'POST':
        raise Http404
    album = Albums.objects.get(slug=album_slug)
    if request.user.username_slug != album.owner.username_slug:
        raise Http404

    if not redis_instance.exists(f"album_{album.pk}"):
        photos_slugs = [photo.slug for photo in album.photos_set.filter(is_private=False)]
        redis_instance.rpush(f"album_{album.pk}_photos", *photos_slugs)
        redis_instance.expire(f"album_{album.pk}_photos", REDIS_DATA_EXPIRATION_SECONDS)

    if not (redis_instance.hget(f"album_{album.pk}", "current_stage") == 1 and
            redis_instance.hget(f"album_{album.pk}", "status") == "processing"):
        redis_instance.hset(f"album_{album.pk}", "current_stage", 1)
        redis_instance.hset(f"album_{album.pk}", "status", "processing")
        redis_instance.hset(f"album_{album.pk}", "number_of_processed_photos", 0)
        redis_instance.expire(f"album_{album.pk}", REDIS_DATA_EXPIRATION_SECONDS)
        face_searching_task.delay(album.pk)

    return redirect('frames_waiting', album_slug=album_slug)


class AlbumFramesWaitingView(LoginRequiredMixin, DetailView):
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/frames_waiting.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404

        if current_stage != 1:
            raise Http404

        return super().get(request, *args, **kwargs)

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
            'first_photo_slug': redis_instance.lindex(f"album_{self.object.pk}_photos", 0),
            'heading': "Searching for faces on album's photos",
            'current_stage': 1,
            'total_stages': 6,
            'instructions': instructions,
            'is_ready': is_ready,
            'title': title,
            'number_of_processed_photos': number_of_processed_photos,
            'button_label': "Verify frames",
            'success_url': reverse_lazy('verify_frames', kwargs={'album_slug': self.object.slug,
                                                                 'photo_slug': first_photo_slug}),
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

        if request.user.username_slug != self.album.owner.username_slug or self.object.is_private:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.album.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 2 and redis_instance.hget(f"album_{self.album.pk}", "status") == "processing" or
                current_stage == 1 and redis_instance.hget(f"album_{self.album.pk}", "status") == "completed"):
            raise Http404

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.album = Albums.objects.get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        if request.user.username_slug != self.album.owner.username_slug or self.object.is_private:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.album.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 2 and redis_instance.hget(f"album_{self.album.pk}", "status") == "processing" or
                current_stage == 1 and redis_instance.hget(f"album_{self.album.pk}", "status") == "completed"):
            raise Http404

        # Base Form method post
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'faces_amount': int(redis_instance.hget(f"photo_{self.object.pk}", "faces_amount"))})

        return kwargs

    def form_valid(self, form):
        self._delete_wrong_data(form)
        self._renumber_faces()
        self._set_correct_status()

        # If this photo is the last one
        if self.object.slug == redis_instance.lindex(f"album_{self.object.album.pk}_photos", -1):
            self._send_faces_to_relate()

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

    def _set_correct_status(self):
        redis_instance.hincrby(f"album_{self.album.pk}", "number_of_processed_photos")

        if int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == 1 and \
                self.object.slug == redis_instance.lindex(f"album_{self.object.pk}_photos", 0):
            redis_instance.hset(f"album_{self.album.pk}", "current_stage", 2)
            redis_instance.hset(f"album_{self.album.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)
        elif int(redis_instance.hget(f"album_{self.album.pk}", "current_stage")) == 2 and \
                self.object.slug == redis_instance.lindex(f"album_{self.object.album.pk}_photos", -1):
            redis_instance.hset(f"album_{self.album.pk}", "status", "completed")
            redis_instance.hset(f"album_{self.album.pk}", "number_of_processed_photos", 0)
            redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def get_success_url(self):
        if self.object.slug == redis_instance.lindex(f"album_{self.object.album.pk}_photos", -1):
            return reverse_lazy('patterns_waiting', kwargs={'album_slug': self.album.slug})
        else:
            next_photo_slug = redis_instance.lindex(
                f"album_{self.object.album.pk}_photos",
                redis_instance.lpos(f"album_{self.object.album.pk}_photos", self.object.slug) + 1,
            )
            return reverse_lazy('verify_frames', kwargs={'album_slug': self.album.slug, 'photo_slug': next_photo_slug})

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        current_photo_number = int(redis_instance.hget(f"album_{self.album.pk}", "number_of_processed_photos")) + 1
        public_photos = self.album.photos_set.all().count()
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
            'heading': f"Verifying photo {self.object.title} ({current_photo_number}/{public_photos})",
            'instructions': instructions,
            'photo_with_frames_url': os.path.join('/media/temp_photos',
                                                  f'album_{self.album.pk}/frames',
                                                  f"photo_{self.object.pk}.jpg"),
            'button_label': button_label,
        })

        return context

    def _send_faces_to_relate(self):
        redis_instance.hset(f"album_{self.album.pk}", "current_stage", 3)
        redis_instance.hset(f"album_{self.album.pk}", "status", "processing")
        redis_instance.expire(f"album_{self.album.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        relate_faces_task.delay(self.album.pk)


class AlbumPatternsWaitingView(LoginRequiredMixin, DetailView):
    model = Albums
    context_object_name = 'album'
    slug_url_kwarg = 'album_slug'
    template_name = 'recognition/patterns_waiting.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if current_stage != 3:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        status = redis_instance.hget(f"album_{self.object.pk}", "status")
        if status == "processing":
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
            'current_stage': 3,
            'total_stages': 6,
            'instructions': instructions,
            'button_label': "Verify results",
            'success_url': reverse_lazy('verify_patterns', kwargs={'album_slug': self.object.slug}),
        })

        return context


class AlbumVerifyPatternsView(LoginRequiredMixin, FormMixin, DetailView):
    template_name = 'recognition/verify_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = BaseVerifyPatternForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 3 and redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == 4 and redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

        self._set_faces_amounts()
        try:
            self._number_of_verified_patterns = int(redis_instance.hget(f"album_{self.object.pk}",
                                                                        "number_of_verified_patterns"))
        except TypeError:
            self._number_of_verified_patterns = 0

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._number_of_verified_patterns,
                                            album_pk=self.object.pk)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 3 and redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == 4 and redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

        form = self.get_form()
        self._set_faces_amounts()
        try:
            self._number_of_verified_patterns = int(redis_instance.hget(f"album_{self.object.pk}",
                                                                        "number_of_verified_patterns"))
        except TypeError:
            self._number_of_verified_patterns = 0

        VerifyPatternFormset = formset_factory(self.form_class,
                                               formset=BaseVerifyPatternFormset,
                                               extra=len(self._faces_amounts))
        self.formset = VerifyPatternFormset(request.POST, faces_amounts=self._faces_amounts,
                                            number_of_verified_patterns=self._number_of_verified_patterns,
                                            album_pk=self.object.pk)

        if self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'title': f'Album \"{self.object}\" - verifying patterns',
            'formset': self.formset,
            'heading': "Verifying patterns of people's faces.",
            'current_stage': 4,
            'total_stages': 6,
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

    def form_valid(self, form):
        path = os.path.join(MEDIA_ROOT, 'temp_photos', f'album_{self.object.pk}/patterns')
        patterns_amount = len(self._faces_amounts)
        patterns_amount = self._replace_odd_faces_to_new_pattern(patterns_amount=patterns_amount,
                                                                 patterns_dir=path)
        self._renumber_patterns_faces_data_and_files(patterns_amount=patterns_amount,
                                                     patterns_dir=path)
        self._set_correct_status()
        return super().form_valid(form)

    def get_success_url(self):
        if self.formset.has_changed():
            return reverse_lazy('verify_patterns', kwargs={'album_slug': self.object.slug})
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

            if self.formset.forms[i-1].fields:
                redis_instance.hincrby(f"album_{self.object.pk}", "number_of_verified_patterns")

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

    def _set_correct_status(self):
        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == 3:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", 4)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == 4 and \
                not self.formset.has_changed():
            redis_instance.hset(f"album_{self.object.pk}", "status", "completed")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)


class AlbumGroupPatternsView(LoginRequiredMixin, FormMixin, DetailView):
    template_name = 'recognition/group_patterns.html'
    model = Albums
    slug_url_kwarg = 'album_slug'
    form_class = GroupPatternsForm
    context_object_name = 'album'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 4 and redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == 5 and redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.user.username_slug != self.object.owner.username_slug:
            raise Http404

        try:
            current_stage = int(redis_instance.hget(f"album_{self.object.pk}", "current_stage"))
        except TypeError:
            raise Http404
        if not (current_stage == 4 and redis_instance.hget(f"album_{self.object.pk}", "status") == "completed" or
                current_stage == 5 and redis_instance.hget(f"album_{self.object.pk}", "status") == "processing"):
            raise Http404

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
            'current_stage': 5,
            'total_stages': 6,
            'instructions': ["Please mark faces belonging to the one same person."],
            'button_label': "Confirm",
        })

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'single_patterns': self._get_single_patterns(),
                       'album_pk': self.object.pk})
        return kwargs

    def _get_single_patterns(self):
        single_patterns = []
        for x in range(1, int(redis_instance.hget(f"album_{self.object.pk}", "number_of_verified_patterns")) + 1):
            if not redis_instance.hexists(f"album_{self.object.pk}_pattern_{x}", "person"):
                single_patterns.append(x)
        return tuple(single_patterns)

    def form_valid(self, form):
        self._group_patterns_into_people(form)
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
        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == 4:
            redis_instance.hset(f"album_{self.object.pk}", "current_stage", 5)
            redis_instance.hset(f"album_{self.object.pk}", "status", "processing")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

        if int(redis_instance.hget(f"album_{self.object.pk}", "current_stage")) == 5 and \
                not any(form.cleaned_data.values()):
            redis_instance.hset(f"album_{self.object.pk}", "status", "completed")
            redis_instance.expire(f"album_{self.object.pk}", REDIS_DATA_EXPIRATION_SECONDS)

    def get_success_url(self):
        if self._get_single_patterns():
            return reverse_lazy('group_patterns', kwargs={'album_slug': self.object.slug})
        else:
            return reverse_lazy('recognition_main')
