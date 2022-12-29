from django.urls import path

from .views import *

urlpatterns = [
    path('logout/', logout_user, name='logout'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('register/', UserRegistrationView.as_view(), name='django_registration_register'),
    path(
        "activate/complete/",
        UserActivationCompleteView.as_view(),
        name="django_registration_activation_complete",
    ),
    path(
        "activate/<str:activation_key>/",
        UserActivationView.as_view(),
        name="django_registration_activate",
    ),
    path(
        "register/complete/",
        UserRegistrationCompleteView.as_view(),
        name="django_registration_complete",
    ),
    path(
        "register/closed/",
        UserRegisterClosedView.as_view(),
        name="django_registration_disallowed",
    ),
    path("password_change/", UserPasswordChangeView.as_view(), name="password_change"),
    path(
        "password_change/done/",
        UserPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("password_reset/", SendMailForPasswordResetView.as_view(), name="password_reset"),
    path(
        "password_reset/done/",
        SendMailForPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        NewPasswordResetView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        NewPasswordResetDoneView.as_view(),
        name="password_reset_complete",
    ),
    path('<slug:username_slug>', UserProfileView.as_view(), name='user_profile'),
    path('<slug:username_slug>/settings', SettingsView.as_view(), name='user_settings'),
]
