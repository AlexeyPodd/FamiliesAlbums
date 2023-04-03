from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, DetailView
from django_registration.backends.activation.views import RegistrationView, ActivationView

from .forms import *


class UserLoginView(auth_views.LoginView):
    form_class = LoginUserForm
    template_name = 'accounts/login.html'
    extra_context = {'title': 'Sing in',
                     'current_section': 'login',
                     'button_label': 'Log in'}

    def get_success_url(self):
        next = self.request.GET.get('next')
        if next:
            return next

        return reverse_lazy('main')


def logout_user(request):
    logout(request)
    return redirect('main')


class UserRegistrationView(RegistrationView):
    form_class = SignupForm
    extra_context = {'title': 'Sing up',
                     'current_section': 'signup',
                     'button_label': 'Sign up'}


class UserRegistrationCompleteView(TemplateView):
    template_name = "django_registration/registration_complete.html"
    extra_context = {'title': 'Registration almost complete'}


class UserActivationView(ActivationView):
    extra_context = {'title': 'Activation fails'}


class UserActivationCompleteView(TemplateView):
    template_name = "django_registration/activation_complete.html"
    extra_context = {'title': 'Activation complete'}


class UserRegisterClosedView(TemplateView):
    template_name = "django_registration/registration_closed.html"
    extra_context = {'title': 'Register closed'}


class SendMailForPasswordResetView(auth_views.PasswordResetView):
    form_class = SendMailForPasswordResetForm
    template_name = 'accounts/password_reset.html'
    extra_context = {'title': 'Password Reset', 'button_label': 'Send email instructions'}


class SendMailForPasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'
    extra_context = {'title': 'Password reset sent'}


class NewPasswordResetView(auth_views.PasswordResetConfirmView):
    template_name = 'accounts/new_password_set.html'
    form_class = ResetPasswordForm
    extra_context = {'title': 'Password reset', 'button_label': 'Change my password'}


class NewPasswordResetDoneView(auth_views.PasswordResetCompleteView):
    template_name = 'accounts/new_password_set_done.html'
    extra_context = {'title': 'Password reset complete'}


class UserPasswordChangeView(auth_views.PasswordChangeView):
    template_name = 'accounts/password_change.html'
    form_class = UserPasswordChangeForm
    extra_context = {'title': 'Password change', 'button_label': 'Change my password'}


class UserPasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = 'accounts/password_change_done.html'
    extra_context = {'title': 'Password change successful'}


class SettingsView(LoginRequiredMixin, UpdateView):
    template_name = 'accounts/settings.html'
    slug_url_kwarg = 'username_slug'
    model = User
    form_class = ProfileSettingsForm

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.username_slug != self.kwargs['username_slug']:
            raise Http404

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.username_slug != self.kwargs['username_slug']:
            raise Http404

        return super().post(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.model.objects.get(username_slug=self.kwargs['username_slug'])

    def form_valid(self, form):
        self.object = form.save()
        if self.object.avatar and form.cleaned_data.get('delete_avatar'):
            self.object.avatar.delete()

        if not form.cleaned_data.get('delete_avatar') and form.cleaned_data.get('avatar'):
            self.object.avatar.delete()
            self.object.avatar = form.files.get('avatar')

        self.object.save()

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({'title': 'Profile settings',
                        'button_label': 'Save changes',
                        'current_section': 'profile_settings',
                        })
        return context

    def get_success_url(self):
        return reverse_lazy('user_profile', kwargs={'username_slug': self.request.user.username_slug})


class UserProfileView(DetailView):
    model = User
    context_object_name = 'owner'
    template_name = 'accounts/profile.html'
    slug_url_kwarg = 'username_slug'

    def get_object(self, queryset=None):
        return self.model.objects.get(username_slug=self.kwargs['username_slug'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            title = 'My profile'
            context.update({'current_section': 'profile'})
        else:
            title = f"{self.kwargs.get('username_slug')}'s profile"

        context.update({'title': title})
        return context
