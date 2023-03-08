import os
import re

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseNotFound, Http404, HttpResponseRedirect, FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, CreateView, UpdateView
from django.views.generic.detail import SingleObjectMixin, DetailView
from django.db.models import Count

from accounts.models import User
from photoalbums.settings import ALBUMS_AMOUNT_LIMIT, ALBUM_PHOTOS_AMOUNT_LIMIT
from .forms import *
from .utils import get_zip, delete_from_favorites, FavoritesPaginator, AboutPageInfo
from .tasks import album_deletion_task


class MainPageView(ListView):
    model = Albums
    template_name = 'mainapp/index.html'
    context_object_name = 'albums'
    extra_context = {'title': 'Main Page'}

    def get_queryset(self):
        return self.model.objects.filter(
            is_private=False,
            photos__isnull=False,
        ).select_related(
            'owner',
            'miniature',
        ).annotate(
            Count('photos'),
        ).order_by(
            '-time_update',
        )[:16]


class AboutPageView(TemplateView):
    template_name = 'mainapp/about.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        general_info = AboutPageInfo(section_id="general",
                                     text_first=False,
                                     img_url=static('images/about.jpg'),
                                     title="About this site",
                                     paragraphs=[
                                         "This site was created to preserve the moments that are important to us, "
                                         "and the memory of the people with whom we spent them.",
                                         "And to search for the lost. Perhaps some of your photos show a person whose"
                                         " photos were lost by their loved ones. If you let them, they can copy these"
                                         " photos!",
                                     ])
        uploads_info = AboutPageInfo(section_id="uploads",
                                     text_first=True,
                                     img_url=static('images/uploads.jpg'),
                                     title="Uploading photos",
                                     paragraphs=[
                                         "We recommend storing your valuable photos in several places to prevent loss "
                                         "due to accidents. This site could be one of those places.",
                                         "Today we can't store ultra-high resolution photos, so if the photo size"
                                         " exceeds 1280 pixels, it will be compressed to that size.",
                                         "We would like to have a friendly community on the site and expect all"
                                         " publicly available content uploaded by our users to be family friendly."
                                         " Please stick to this rule.",
                                     ])
        recognition_info = AboutPageInfo(section_id="recognition",
                                         text_first=False,
                                         img_url=static('images/recognition.jpg'),
                                         title="Recognition",
                                         paragraphs=[
                                             "If you want to find photos with your relative that you don't have...",
                                             "Or just let other users search your photos based on the people in them...",
                                             "You should process your album to identify the people in it. This process "
                                             "is mostly automatic, requiring only a very simple confirmation of the "
                                             "result from you, which even a child can handle.",
                                             "We hope that this application will allow you to bring back precious"
                                             " memories for you. If you don't succeed right away, don't despair! "
                                             "Perhaps some new user will one day find their loved ones in your photo. "
                                             "And maybe he will also have photos of yours that you don't have!",
                                         ])

        context.update({
            'title': 'About this site',
            'current_section': 'about',
            'sections_info': (general_info, uploads_info, recognition_info),
        })

        return context


def pageNotFound(request, exception):
    return HttpResponseNotFound('<h1>Page not found</h1>')


class UserAlbumsView(ListView):
    model = Albums
    template_name = 'mainapp/albums.html'
    context_object_name = 'albums'
    paginate_by = 12

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs['username_slug']:
            queryset = self.model.objects.filter(owner__pk=self.request.user.pk).select_related('miniature', 'owner').annotate(Count('photos'))
        else:
            queryset = self.model.objects.filter(owner__username_slug=self.kwargs['username_slug'], is_private=False).select_related('miniature', 'owner').annotate(Count('photos'))
            if not queryset:
                raise Http404
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs['username_slug']:
            context.update({
                'title': 'My albums', 'current_section': 'my_albums',
                'limit': ALBUMS_AMOUNT_LIMIT,
                'limit_reached': len(self.object_list) >= ALBUMS_AMOUNT_LIMIT,
            })
        else:
            context.update({'title': f"{self.kwargs['username_slug']}'s albums"})

        context.update({'owner_slug': self.kwargs['username_slug']})
        return context


class AlbumView(SingleObjectMixin, ListView):
    template_name = 'mainapp/album_photos.html'
    slug_url_kwarg = 'album_slug'
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=Albums.objects.filter(owner__username_slug=kwargs['username_slug']))

        if (not request.user.is_authenticated or request.user.username_slug != kwargs['username_slug']) and \
                self.object.is_private:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': f'Album \"{self.object.title}\"',
            'album': self.object,
            'owner_slug': self.kwargs['username_slug'],
        })
        
        if self.request.user.is_authenticated:
            context.update({'in_favorites': self.object.in_users_favorites.filter(username_slug=self.request.user.username_slug).exists()})
        
        return context

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs['username_slug']:
            queryset = self.object.photos_set.all()
        else:
            queryset = self.object.photos_set.filter(is_private=False)
        return queryset


class PhotoView(DetailView):
    model = Photos
    template_name = 'mainapp/photo.html'
    context_object_name = 'photo'
    slug_url_kwarg = 'photo_slug'

    def get(self, request, *args, **kwargs):
        self.album = Albums.objects.get(slug=kwargs['album_slug'])
        self.object = self.get_object(queryset=self.model.objects.filter(album_id=self.album.pk))

        if (not request.user.is_authenticated or request.user.username_slug != kwargs['username_slug']) and \
                self.object.is_private:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': f'\"{self.object.title}\" ({self.album.title})',
            'album': self.album,
            'owner_slug': self.kwargs['username_slug'],
            'owner_name': User.objects.get(username_slug=self.kwargs['username_slug']).username,
            'previous_photo_url': self._get_neighbor_photo_url(right=False),
            'next_photo_url': self._get_neighbor_photo_url(right=True),
        })
        
        if self.request.user.is_authenticated:
            in_favorites = self.object.in_users_favorites.filter(username_slug=self.request.user.username_slug).exists() or\
                self.object.album.in_users_favorites.filter(username_slug=self.request.user.username_slug).exists()
            context.update({'in_favorites': in_favorites})
            
        return context

    def _get_neighbor_photo_url(self, right: bool):
        show_private = self.request.user.is_authenticated and \
                       self.request.user.username_slug == self.kwargs['username_slug']
        get_photo = self.object.get_next_by_time_create if right else self.object.get_previous_by_time_create

        def get_neighbor_photo():
            if show_private:
                return get_photo(album_id=self.album.pk)
            else:
                return get_photo(album_id=self.album.pk, is_private=False)

        try:
            neighbor_photo = get_neighbor_photo()
        except ObjectDoesNotExist:
            return
            
        return reverse('photo', kwargs={'username_slug': self.kwargs['username_slug'],
                                        'album_slug': self.album.slug,
                                        'photo_slug': neighbor_photo.slug})


class AlbumCreateView(LoginRequiredMixin, CreateView):
    form_class = AlbumCreateForm
    template_name = 'mainapp/album_create.html'

    def get(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            return redirect('create_album', username_slug=request.user.username_slug)

        self._check_albums_amount_limit()

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            return redirect('create_album', username_slug=request.user.username_slug)

        self._check_albums_amount_limit()

        return super().post(request, *args, **kwargs)

    def _check_albums_amount_limit(self):
        created_albums_amount = self.form_class.Meta.model.objects.filter(
            owner__username_slug=self.request.user.username_slug,
        ).count()
        if created_albums_amount >= ALBUMS_AMOUNT_LIMIT:
            raise Http404

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'owner_slug': self.request.user.username_slug,
                        'title': 'Create new album',
                        'button_label': 'Create'})
        return context

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs.update({'user': self.request.user})
        return form_kwargs

    def form_valid(self, form):
        # Validating amount of uploaded photos
        if len(self.request.FILES.getlist('images')) > ALBUM_PHOTOS_AMOUNT_LIMIT:
            msg = f"You can upload only {ALBUM_PHOTOS_AMOUNT_LIMIT} photos in each album"
            form.add_error('images', msg)
            return self.form_invalid(form)

        form.instance.owner_id = self.request.user.pk

        self.object = form.save()
        self._add_images_to_album_object(form)
        self._set_random_album_cover()

        return super().form_valid(form)

    def _add_images_to_album_object(self, form):
        images = self.request.FILES.getlist('images')
        for image in images:
            photo = Photos(title=self._get_photos_title(image.name),
                           date_start=form.cleaned_data['date_start'],
                           date_end=form.cleaned_data['date_end'],
                           location=form.cleaned_data['location'],
                           is_private=form.cleaned_data['is_private'],
                           album=self.object,
                           original=image)
            self.object.photos_set.add(photo, bulk=False)

    def _set_random_album_cover(self):
        cover = self.object.photos_set.order_by('?').first()
        if cover:
            self.object.miniature = cover

    @staticmethod
    def _get_photos_title(filename):
        return filename[:filename.rindex('.')]

    def get_success_url(self):
        return reverse_lazy('album_edit', kwargs={'username_slug': self.request.user.username_slug,
                                                  'album_slug': self.object.slug})


class AlbumEditView(LoginRequiredMixin, UpdateView):
    template_name = 'mainapp/album_edit.html'
    slug_url_kwarg = 'album_slug'
    form_class = AlbumEditForm
    model = Albums
    context_object_name = 'album'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({'title': f'Edit album \"{self.object.title}\"',
                        'owner_slug': self.request.user.username_slug,
                        'button_label': 'Save changes',
                        'photos_formset': self.photos_formset,
                        })
        return context

    def get(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            return redirect('album', username_slug=self.kwargs['username_slug'], album_slug=self.kwargs['album_slug'])

        self.object = self.get_object()
        self.photos_formset = PhotosInlineFormset(instance=self.object)

        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            return redirect('album', username_slug=self.kwargs['username_slug'], album_slug=self.kwargs['album_slug'])

        self.object = self.get_object()
        form = self.get_form()
        self.photos_formset = PhotosInlineFormset(request.POST, instance=self.object)

        if request.POST.get('delete', False):
            album_deletion_task.delay(self.object.pk)
            return redirect('user_albums', username_slug=self.kwargs['username_slug'])

        if form.is_valid() and self.photos_formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs.update({'user': self.request.user,
                            'album': self.object})
        return form_kwargs

    def get_success_url(self):
        if self.request.FILES:
            return reverse_lazy('album_edit', kwargs={'username_slug': self.request.user.username_slug,
                                                      'album_slug': self.object.slug})
        return reverse_lazy('album', kwargs={'username_slug': self.request.user.username_slug,
                                             'album_slug': self.object.slug})

    def form_valid(self, form):
        # Validating dates of album and it's photos:
        if not self._check_dates_match(form):
            return self.form_invalid(form)

        # Validating amount of uploaded photos
        if self.object.photos_set.count() + len(self.request.FILES.getlist('images')) > ALBUM_PHOTOS_AMOUNT_LIMIT:
            msg = f"You can upload only {ALBUM_PHOTOS_AMOUNT_LIMIT} photos in each album"
            form.add_error('images', msg)
            return self.form_invalid(form)

        self.object = form.save()

        # Adding uploaded photos to album and choosing random cover
        had_photos = self.object.photos_set.exists()
        self._add_images_to_album_object(form)
        if not had_photos:
            self._set_random_album_cover()

        self.photos_formset.save()

        need_new_cover = False

        # deleting marked objects
        for delete_value in self.photos_formset.deleted_objects:
            if delete_value.pk == self.object.miniature.pk:
                need_new_cover = True
            delete_value.delete()

        # check if old cover become private
        self.object = self.get_object()
        if self.object.miniature and not self.object.is_private and self.object.miniature.is_private:
            need_new_cover = True

        # Set new album cover, if needed
        if need_new_cover:
            cover = self.object.photos_set.filter(is_private=False).order_by('?').first()
            if cover:
                self.object.miniature = cover
                self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def _check_dates_match(self, form):
        is_valid = True
        earliest_photo_forms = sorted(
            (photo_form for photo_form in self.photos_formset if photo_form.cleaned_data.get('date_start')),
            key=lambda f: f.cleaned_data.get('date_start')
        )
        latest_photo_forms = sorted(
            (photo_form for photo_form in self.photos_formset if photo_form.cleaned_data.get('date_end')),
            key=lambda f: f.cleaned_data.get('date_end'),
            reverse=True
        )

        if form.cleaned_data.get('date_start') and earliest_photo_forms and \
                form.cleaned_data.get('date_start') > earliest_photo_forms[0].cleaned_data['date_start']:
            form.add_error('date_start', 'There is a photo with an earlier date.')
            earliest_photo_forms[0].add_error('date_start', 'This date does not match the album date period.')
            is_valid = False

        if form.cleaned_data.get('date_end') and latest_photo_forms and \
                form.cleaned_data.get('date_end') < latest_photo_forms[0].cleaned_data['date_end']:
            form.add_error('date_end', 'There is a photo with an later date.')
            latest_photo_forms[0].add_error('date_end', 'This date does not match the album date period.')
            is_valid = False

        return is_valid

    def _add_images_to_album_object(self, form):
        images = self.request.FILES.getlist('images')
        for image in images:
            photo = Photos(title=self._get_photos_title(image.name),
                           date_start=form.cleaned_data['date_start'],
                           date_end=form.cleaned_data['date_end'],
                           location=form.cleaned_data['location'],
                           is_private=form.cleaned_data['is_private'],
                           album=self.object,
                           original=image)
            self.object.photos_set.add(photo, bulk=False)

    def _set_random_album_cover(self):
        cover = self.object.photos_set.order_by('?').first()
        if cover:
            self.object.miniature = cover

    @staticmethod
    def _get_photos_title(filename):
        return filename[:filename.rindex('.')]


def download(request):
    if request.method != 'GET' or not (request.GET.get('photo') or request.GET.get('album')):
        raise Http404

    if request.GET.get('album'):
        album_slug = request.GET.get('album')
        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            return HttpResponse(status=204)

        private_access = request.user.is_authenticated and request.user.username_slug == album.owner.username_slug

        if album.is_private and not private_access:
            return HttpResponse(status=204)

        if not album.photos_set.exists() or\
                not private_access and not album.photos_set.filter(is_private=False).exists():
            return HttpResponse(status=204)

        zip_wrapper = get_zip(album, private_access=private_access)
        response = FileResponse(zip_wrapper,
                                content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename={album.title}.zip'

        return response

    elif request.GET.get('photo'):
        photo_slug = request.GET.get('photo')
        try:
            photo = Photos.objects.get(slug=photo_slug)
        except ObjectDoesNotExist:
            return HttpResponse(status=204)

        if photo.is_private and \
                (not request.user.is_authenticated or request.user.username_slug != photo.album.owner.username_slug):
            return HttpResponse(status=204)

        return FileResponse(photo.original.open(),
                            as_attachment=True,
                            filename=f'{photo.title}{os.path.splitext(photo.original.url)[-1]}')


class FavoritesView(LoginRequiredMixin, ListView):
    model = Albums
    template_name = 'mainapp/favorites.html'
    context_object_name = 'albums'
    paginate_by = 12
    paginator_class = FavoritesPaginator

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({'title': 'My Favorites',
                        'current_section': 'favorites',
                        })
        return context

    def get(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.filter(in_users_favorites__username_slug=self.request.user.username_slug).select_related('owner')


class FavoritesPhotosView(LoginRequiredMixin, ListView):
    model = Photos
    template_name = 'mainapp/favorites_photos.html'
    context_object_name = 'photos'
    paginate_by = 20

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({'title': 'My Favorites Photos',
                        'current_section': 'favorites',
                        'my_albums': Albums.objects.filter(owner__username_slug=self.request.user.username_slug),
                        })
        return context

    def get(self, request, *args, **kwargs):
        if request.user.username_slug != self.kwargs['username_slug']:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.select_related('album__owner').filter(in_users_favorites__username_slug=self.request.user.username_slug)


@login_required
def add_to_favorites(request):
    if request.method != 'POST':
        raise Http404

    if not request.POST.get('photo') and not request.POST.get('album'):
        return HttpResponse(status=400)

    if request.POST.get('album'):
        album_slug = request.POST.get('album')

        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            raise Http404

        if not album.owner.username_slug == request.user.username_slug and not album.is_private and\
                not album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            album.in_users_favorites.add(request.user)
            album.save()

    if request.POST.get('photo'):
        photo_slug = request.POST.get('photo')

        try:
            photo = Photos.objects.get(slug=photo_slug)
        except ObjectDoesNotExist:
            raise Http404

        if not photo.album.owner.username_slug == request.user.username_slug and not photo.is_private and\
                not photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            photo.in_users_favorites.add(User.objects.get(username_slug=request.user.username_slug))
            photo.save()

    return HttpResponseRedirect(request.POST.get('next', '/'))


@login_required
def remove_from_favorites(request):
    if request.method != 'POST':
        raise Http404

    if not request.POST.get('photo') and not request.POST.get('album'):
        return HttpResponse(status=400)

    if request.POST.get('photo'):
        photo = Photos.objects.get(slug=request.POST.get('photo'))
        delete_from_favorites(request.user, photo)

    if request.POST.get('album'):
        album = Albums.objects.get(slug=request.POST.get('album'))
        delete_from_favorites(request.user, album)

    return HttpResponseRedirect(request.POST.get('next', '/'))


@login_required
def save_photo_to_album(request):
    if request.method != 'POST':
        raise Http404

    regex = re.compile(r'^photo:([^ ]+?), album:([^ ]+?)$')
    data = request.POST.get('data')
    if not data or not re.fullmatch(regex, data):
        return HttpResponse(status=400)

    photo_slug, album_slug = re.search(regex, data).groups()

    try:
        album = Albums.objects.get(slug=album_slug)
        photo = Photos.objects.get(slug=photo_slug)
    except ObjectDoesNotExist:
        raise Http404

    if not photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
        return HttpResponse(status=400)

    if Photos.objects.filter(album_id=album.pk, original=photo.original).exists():
        return HttpResponse(status=204)

    delete_from_favorites(request.user, photo)

    photo.pk, photo.id = None, None
    photo.faces_extracted = False
    photo._state.adding = True
    photo.album = album
    photo.is_private = album.is_private
    photo.save()

    return HttpResponseRedirect(request.POST.get('next', '/'))


@login_required
def save_album(request):
    if request.method != 'POST':
        raise Http404

    album_slug = request.POST.get('album')
    if not album_slug:
        HttpResponse(status=400)

    try:
        album = Albums.objects.get(slug=album_slug, is_private=False)
    except ObjectDoesNotExist:
        raise Http404

    if not album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
        return HttpResponse(status=400)

    delete_from_favorites(request.user, album)

    album.pk, album.id = None, None
    album._state.adding = True
    album.owner = request.user
    album.miniature = None
    album.save()

    for photo in Photos.objects.filter(album__slug=album_slug, is_private=False):
        photo.pk, photo.id = None, None
        photo.faces_extracted = False
        photo._state.adding = True
        photo.album = album
        photo.save()

    album.miniature = Photos.objects.get(original=Albums.objects.get(slug=album_slug).miniature.original, album=album)
    album.save()

    return redirect('user_albums', username_slug=request.user.username_slug)
