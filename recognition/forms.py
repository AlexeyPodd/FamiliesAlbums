from django import forms


class VerifyFramesForm(forms.Form):
    def __init__(self, *args, faces_amount=0, **kwargs):
        super().__init__(*args, **kwargs)

        for i in range(faces_amount):
            self.fields[f'face_{i+1}'] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                  'style': 'width: 25px; height: 25px;'}),
                label=f'face {i+1}',
                required=False,
            )
