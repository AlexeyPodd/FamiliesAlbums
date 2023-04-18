from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError


class ResetPasswordProxyForm(forms.Form):
    error_messages = {
        "password_mismatch": "The two password fields didn’t match.",
    }

    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password",
                                          'class': 'form-control',
                                          'placeholder': 'new_password1'}),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password",
                                          'class': 'form-control',
                                          'placeholder': 'new_password2'}),
    )

    def clean_new_password2(self):
        password1 = self.cleaned_data.get("new_password1")
        password2 = self.cleaned_data.get("new_password2")
        if password1 and password2:
            if password1 != password2:
                raise ValidationError(
                    self.error_messages["password_mismatch"],
                    code="password_mismatch",
                )
        return password2
