from django.test import SimpleTestCase
from django.urls import reverse, resolve

from accounts.views import SettingsView, NewPasswordResetDoneView, UserProfileView, NewPasswordResetView, \
    SendMailForPasswordResetDoneView, SendMailForPasswordResetView, UserPasswordChangeDoneView, UserPasswordChangeView, \
    UserRegisterClosedView, UserRegistrationCompleteView, UserActivationView, UserActivationCompleteView, \
    UserRegistrationView, UserLoginView, logout_user


class TestUrls(SimpleTestCase):
    def test_logout_url_is_resolves(self):
        url = reverse('logout')
        self.assertEqual(resolve(url).func, logout_user)

    def test_login_url_is_resolves(self):
        url = reverse('login')
        self.assertEqual(resolve(url).func.view_class, UserLoginView)

    def test_django_registration_register_url_is_resolves(self):
        url = reverse('django_registration_register')
        self.assertEqual(resolve(url).func.view_class, UserRegistrationView)

    def test_django_registration_activation_complete_url_is_resolves(self):
        url = reverse('django_registration_activation_complete')
        self.assertEqual(resolve(url).func.view_class, UserActivationCompleteView)

    def test_django_registration_activate_url_is_resolves(self):
        url = reverse('django_registration_activate', kwargs={'activation_key': 'some-key'})
        self.assertEqual(resolve(url).func.view_class, UserActivationView)

    def test_django_registration_complete_url_is_resolves(self):
        url = reverse('django_registration_complete')
        self.assertEqual(resolve(url).func.view_class, UserRegistrationCompleteView)

    def test_django_registration_disallowed_url_is_resolves(self):
        url = reverse('django_registration_disallowed')
        self.assertEqual(resolve(url).func.view_class, UserRegisterClosedView)

    def test_password_change_url_is_resolves(self):
        url = reverse('password_change')
        self.assertEqual(resolve(url).func.view_class, UserPasswordChangeView)

    def test_password_change_done_url_is_resolves(self):
        url = reverse('password_change_done')
        self.assertEqual(resolve(url).func.view_class, UserPasswordChangeDoneView)

    def test_password_reset_url_is_resolves(self):
        url = reverse('password_reset')
        self.assertEqual(resolve(url).func.view_class, SendMailForPasswordResetView)

    def test_password_reset_done_url_is_resolves(self):
        url = reverse('password_reset_done')
        self.assertEqual(resolve(url).func.view_class, SendMailForPasswordResetDoneView)

    def test_password_reset_confirm_url_is_resolves(self):
        url = reverse('password_reset_confirm', args=['some-uidb64', 'some-token'])
        self.assertEqual(resolve(url).func.view_class, NewPasswordResetView)

    def test_password_reset_complete_url_is_resolves(self):
        url = reverse('password_reset_complete')
        self.assertEqual(resolve(url).func.view_class, NewPasswordResetDoneView)

    def test_user_profile_url_is_resolves(self):
        url = reverse('user_profile', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, UserProfileView)

    def test_user_settings_url_is_resolves(self):
        url = reverse('user_settings', kwargs={'username_slug': 'some-username-slug'})
        self.assertEqual(resolve(url).func.view_class, SettingsView)
