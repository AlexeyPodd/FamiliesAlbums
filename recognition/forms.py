from django import forms

from .utils import VerifyMatchField


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
        if index >= self._number_of_verified_patterns:
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

        for new_people_inds, old_people_pks, new_per_url, old_per_url in match_imgs_urls:
            self.fields[f'pair_{new_people_inds}_{old_people_pks}'] = VerifyMatchField(
                new_per_img=new_per_url,
                old_per_img=old_per_url,
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                  'style': 'width: 25px; height: 25px;'}),
                label=f'pair_{new_people_inds}_{old_people_pks}',
                required=False,
            )


class ManualMatchingForm(forms.Form):
    done = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                          'style': 'width: 25px; height: 25px;'}),
        label="Here is no matches.",
        required=False,
    )

    def __init__(self, new_ppl, old_ppl, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['new_person'] = forms.ChoiceField(
            widget=forms.RadioSelect(attrs={'class': 'form-check-input',
                                            'style': 'width: 25px; height: 25px;'}),
            label="Not matched people of this album",
            choices=[(ind, url) for ind, url in new_ppl],
        )

        self.fields['old_person'] = forms.ChoiceField(
            widget=forms.RadioSelect(attrs={'class': 'form-check-input',
                                            'style': 'width: 25px; height: 25px;'}),
            label="Previously created people",
            choices=[(pk, url) for pk, url in old_ppl],
        )
