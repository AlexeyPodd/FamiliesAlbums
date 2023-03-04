from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth import forms as auth_forms
from django_registration.forms import RegistrationForm

from .models import User


class LoginUserForm(auth_forms.AuthenticationForm):
    username = forms.CharField(label='Username',
                               widget=forms.TextInput(attrs={'class': 'form-control',
                                                             'placeholder': 'name'}))
    password = forms.CharField(label='Password',
                               widget=forms.PasswordInput(attrs={'class': 'form-control',
                                                                 'placeholder': 'password'}))


class SignupForm(RegistrationForm):
    username = forms.CharField(label='Username',
                               widget=forms.TextInput(attrs={'class': 'form-control',
                                                             'placeholder': 'name'}))
    email = forms.EmailField(label='Email',
                             widget=forms.EmailInput(attrs={'class': 'form-control',
                                                            'placeholder': 'email'}))
    password1 = forms.CharField(label='Password',
                                widget=forms.PasswordInput(attrs={'class': 'form-control',
                                                                  'placeholder': 'password1'}))
    password2 = forms.CharField(label='Password confirmation',
                                widget=forms.PasswordInput(attrs={'class': 'form-control',
                                                                  'placeholder': 'password2'}))
    agreement = forms.BooleanField(label='I agree to be bound by the terms of use agreement',
                                   widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta(RegistrationForm.Meta):
        model = User


class SendMailForPasswordResetForm(auth_forms.PasswordResetForm):
    email = forms.EmailField(label="Email address",
                             max_length=254,
                             widget=forms.EmailInput(attrs={"autocomplete": "email",
                                                            'class': 'form-control',
                                                            'placeholder': 'email'}))


class ResetPasswordForm(auth_forms.SetPasswordForm):
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


class UserPasswordChangeForm(auth_forms.PasswordChangeForm):
    old_password = forms.CharField(
        label="Old password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password",
                   "autofocus": True,
                   'class': 'form-control',
                   'placeholder': 'old_password'}
        ),
    )
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
                                          'placeholder': 'new_password1'}),
    )

    field_order = ["old_password", "new_password1", "new_password2"]


class ProfileSettingsForm(forms.ModelForm):
    delete_avatar = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input',
                                                                         'style': 'width: 25px; height: 25px;'}),
                                       label='Delete avatar',
                                       required=False)
    avatar = forms.ImageField(widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
                              label='avatar',
                              required=False)

    field_order = ['avatar', 'delete_avatar', 'about', 'facebook', 'instagram', 'telegram', 'whatsapp']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        contact_fields = ('facebook', 'instagram', 'telegram', 'whatsapp')
        for field in self:
            field.is_contact_field = field.name in contact_fields

    class Meta:
        model = User
        fields = ['about', 'facebook', 'instagram', 'telegram', 'whatsapp']
        labels = {
            'about': 'About myself',
            'facebook': 'facebook',
            'instagram': 'instagram',
            'telegram': 'telegram',
            'whatsapp': 'whatsapp',
        }
        widgets = {
            'about': forms.Textarea(attrs={'class': 'form-control', 'rows': '3'}),
            'facebook': forms.URLInput(attrs={'class': 'form-control'}),
            'instagram': forms.URLInput(attrs={'class': 'form-control'}),
            'telegram': forms.URLInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.URLInput(attrs={'class': 'form-control'}),
        }
