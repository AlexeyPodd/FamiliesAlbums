import os.path

from django import forms

from photoalbums.settings import MEDIA_ROOT


class VerifyFramesForm(forms.Form):
    def __init__(self, *args, faces_amount=0, **kwargs):
        super().__init__(*args, **kwargs)

        for i in range(1, faces_amount + 1):
            self.fields[f'face_{i}'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                  'style': 'width: 25px; height: 25px;'}),
                label=f'face {i}',
                required=False,
            )


class BaseVerifyPatternForm(forms.Form):
    def clean(self):
        super().clean()

        if all(self.cleaned_data.values()):
            msg = "You should choose faces that do not fit the majority in this row. Not all of them."
            self.add_error(None, msg)


class BaseVerifyPatternFormset(forms.BaseFormSet):
    def __init__(self, *args, album_pk, faces_amounts: tuple, number_of_verified_patterns: int, **kwargs):
        super().__init__(*args, **kwargs)
        self._faces_amounts = faces_amounts
        self._number_of_verified_patterns = number_of_verified_patterns
        self._album_pk = album_pk

    def add_fields(self, form, index):
        super().add_fields(form, index)
        if index >= self._number_of_verified_patterns:
            for i in range(1, self._faces_amounts[index] + 1):
                form.fields[f'face_{i}'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                      'style': 'width: 25px; height: 25px;'}),
                    label=f"/media/temp_photos/album_{self._album_pk}/patterns/{index + 1}/{i}.jpg",
                    required=False,
                )
