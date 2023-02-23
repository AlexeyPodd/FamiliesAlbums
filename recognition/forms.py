from django import forms
from django.forms import modelformset_factory

from recognition.models import People


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
    def __init__(self, *args, album_pk, faces_amounts: tuple[int, ...], number_of_verified_patterns: int, **kwargs):
        super().__init__(*args, **kwargs)
        self._faces_amounts = faces_amounts
        self._number_of_verified_patterns = number_of_verified_patterns
        self._album_pk = album_pk

    def add_fields(self, form, index):
        super().add_fields(form, index)
        if index >= self._number_of_verified_patterns and self._faces_amounts[index] > 1:
            for i in range(1, self._faces_amounts[index] + 1):
                form.fields[f'face_{i}'] = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                      'style': 'width: 25px; height: 25px;'}),
                    label=f"/media/temp_photos/album_{self._album_pk}/patterns/{index + 1}/{i}.jpg",
                    required=False,
                )


class GroupPatternsForm(forms.Form):
    def __init__(self, album_pk, single_patterns: tuple[int, ...], *args, **kwargs):
        super().__init__(*args, **kwargs)

        for x in single_patterns:
            self.fields[f'pattern_{x}'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                  'style': 'width: 25px; height: 25px;'}),
                label=f"/media/temp_photos/album_{album_pk}/patterns/{x}/1.jpg",
                required=False,
            )


class VarifyMatchesForm(forms.Form):
    def __init__(self, match_imgs_urls, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for new_people_ind, old_people_pk, *_ in match_imgs_urls:
            self.fields[f'pair_{new_people_ind}_{old_people_pk}'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                  'style': 'width: 35px; height: 35px;'}),
                label=f'new{new_people_ind}_old{old_people_pk}',
                required=False,
            )


class ManualMatchingForm(forms.Form):
    done = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input m-2',
                                          'style': 'width: 25px; height: 25px;'}),
        label="Here is no matches",
        required=False,
    )

    def __init__(self, new_ppl, old_ppl, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['new_ppl'] = forms.ChoiceField(
            widget=forms.RadioSelect(attrs={'class': 'form-check-input',
                                            'style': 'width: 25px; height: 25px;'}),
            label="Not matched people of this album",
            choices=[(ind, url) for ind, url in new_ppl],
            required=False,
        )

        self.fields['old_ppl'] = forms.ChoiceField(
            widget=forms.RadioSelect(attrs={'class': 'form-check-input',
                                            'style': 'width: 25px; height: 25px;'}),
            label="Previously created people",
            choices=[(pk, url) for pk, url in old_ppl],
            required=False,
        )

    def clean(self):
        super().clean()
        new_person_picked = bool(self.cleaned_data.get('new_ppl'))
        old_person_picked = bool(self.cleaned_data.get('old_ppl'))
        done = self.cleaned_data.get('done')

        if not done and (new_person_picked and not old_person_picked or not new_person_picked and old_person_picked):
            self.add_error(None, "Only one person was picked. You should chose pair, or mark \"Here is no matches\".")


RenamePeopleFormset = modelformset_factory(
    People,
    fields=('name',),
    widgets={'name': forms.TextInput(attrs={'class': 'form-control'})}
)
