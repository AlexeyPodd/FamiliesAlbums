from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.forms.formsets import DELETION_FIELD_NAME

from .models import *


class AlbumCreateForm(forms.ModelForm):
    images = forms.ImageField(widget=forms.ClearableFileInput(attrs={'multiple': True, 'class': 'form-control'}),
                              label='Upload photos to album',
                              required=False,
                              validators=[FileExtensionValidator(
                                  allowed_extensions=['png', 'webp', 'jpeg', 'jpg'])],
                              )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        super().clean()

        date_start = self.cleaned_data.get('date_start')
        date_end = self.cleaned_data.get('date_end')
        if date_start and date_end and date_start > date_end:
            msg = "The end of the period can't be earlier than the beginning"
            self.add_error('date_start', msg)
            self.add_error('date_end', msg)

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if Albums.objects.filter(owner_id=self.user.pk, title=title).exists():
            raise ValidationError('You already have album with this title. Please, choose another title for this one.')

        return title

    class Meta:
        model = Albums
        fields = ['title', 'date_start', 'date_end', 'location', 'description', 'is_private', 'images']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'date_start': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                                 attrs={'class': 'form-select w-25'}),
            'date_end': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                               attrs={'class': 'form-select w-25'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control',
                                                 'rows': '3'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'width: 25px; height: 25px;'}),
        }
        labels = {
            'title': "Album's title",
            'date_start': 'Period of time in photos',
            'location': 'Locations in photos',
            'description': 'Detailed description',
            'is_private': 'Mark album as private',
        }


class AlbumEditForm(forms.ModelForm):
    images = forms.ImageField(widget=forms.ClearableFileInput(attrs={'multiple': True, 'class': 'form-control'}),
                              label='Upload photos to album',
                              required=False,
                              validators=[FileExtensionValidator(
                                  allowed_extensions=['png', 'webp', 'jpeg', 'jpg'])],
                              )
    delete = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                                  'style': 'width: 25px; height: 25px;'}),
                                label='Delete album',
                                required=False)

    def __init__(self, user, album, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.album = album
        self.fields['miniature'] = forms.ModelChoiceField(queryset=self._get_queryset_for_miniature(),
                                                          widget=forms.Select(attrs={'class': 'form-select'}),
                                                          label="Album's cover",
                                                          empty_label='Default cover',
                                                          required=False)

    def _get_queryset_for_miniature(self):
        if self.album.is_private:
            return self.album.photos_set.all()
        else:
            return self.album.photos_set.filter(is_private=False)

    def clean(self):
        super().clean()

        date_start = self.cleaned_data.get('date_start')
        date_end = self.cleaned_data.get('date_end')
        if date_start and date_end and date_start > date_end:
            msg = "The end of the period can't be earlier than the beginning"
            self.add_error('date_start', msg)
            self.add_error('date_end', msg)

    def clean_title(self):
        title = self.cleaned_data.get('title')

        namesake_album_queryset = Albums.objects.filter(owner_id=self.user.pk, title=title)
        if namesake_album_queryset.exists() and namesake_album_queryset[0].pk != self.album.pk:
            raise ValidationError('You already have album with this title. Please, choose another title for this one.')

        return title

    def save(self, commit=True):
        instance = super().save(commit=False)

        if instance.is_private != instance.original_is_private:
            for photo in instance.photos_set.all():
                photo.is_private = instance.is_private
                if instance.is_private:
                    photo.in_users_favorites.clear()

                    # Delete all recognized faces
                    if photo.faces_extracted:
                        for face in photo.faces_set.all():
                            face.delete()
                        photo.faces_extracted = False
                photo.save()

            if instance.is_private:
                instance.in_users_favorites.clear()

        if commit:
            instance.save()
        return instance

    class Meta:
        model = Albums
        fields = ['title', 'miniature', 'date_start', 'date_end', 'location', 'description', 'is_private', 'images']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'date_start': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                                 attrs={'class': 'form-select w-25'}),
            'date_end': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                               attrs={'class': 'form-select w-25'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control',
                                                 'rows': '3'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'width: 25px; height: 25px;'}),
        }
        labels = {
            'title': "Album's title",
            'date_start': 'Period of time in photos',
            'location': 'Locations in photos',
            'description': 'Detailed description',
            'is_private': 'Mark album as private',
        }


class CustomInlineFormset(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields[DELETION_FIELD_NAME].widget = forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                                             'style': 'width: 25px; height: 25px;'})

    def save(self, commit=True):
        instances = super().save(commit=False)

        for instance in instances:
            if instance.is_private and not instance.original_is_private:
                # remove from other users favorites
                instance.in_users_favorites.clear()

                # Delete all recognized faces
                if instance.faces_extracted:
                    for face in instance.faces_set.all():
                        face.delete()
                    instance.faces_extracted = False
            if commit:
                instance.save()

        return instances

    def clean(self):
        super().clean()

        for form in self.forms:
            self._clean_dates(form)
            self._clean_location(form)
            self._clean_is_private(form)

    def _clean_dates(self, form):
        date_start = form.cleaned_data.get('date_start')
        date_end = form.cleaned_data.get('date_end')

        if not date_start and self.instance.date_start:
            date_start = self.instance.date_start
            form.cleaned_data['date_start'] = date_start
            form.instance.date_start = date_start

        if not date_end and self.instance.date_end:
            date_end = self.instance.date_end
            form.cleaned_data['date_end'] = date_end
            form.instance.date_end = date_end

        if date_start and date_end and date_start > date_end:
            msg = "The end of the period can't be earlier than the beginning"
            form.add_error('date_start', msg)
            form.add_error('date_end', msg)

    def _clean_location(self, form):
        location = form.cleaned_data.get('location')

        if not location and self.instance.location:
            location = self.instance.location
            form.cleaned_data['location'] = location
            form.instance.location = location

    def _clean_is_private(self, form):
        if self.instance.is_private:
            form.cleaned_data['is_private'] = True
            form.instance.is_private = True


PhotosInlineFormset = inlineformset_factory(
    Albums, Photos,
    formset=CustomInlineFormset,
    fields=('title', 'date_start', 'date_end', 'location', 'description', 'is_private'),
    widgets={'title': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
             'date_start': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                                  attrs={'class': 'form-select form-select-sm w-25'}),
             'date_end': forms.SelectDateWidget(years=range(2030, 1849, -1),
                                                attrs={'class': 'form-select form-select-sm w-25'}),
             'location': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
             'description': forms.Textarea(attrs={'class': 'form-control form-control-sm',
                                                  'rows': '3'}),
             'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                      'style': 'width: 25px; height: 25px;'})},
    labels={
            'title': "Title",
            'date_start': 'Date period',
            'location': 'Location',
            'description': 'Detailed description',
            'is_private': 'Private',
        },
    extra=0)
