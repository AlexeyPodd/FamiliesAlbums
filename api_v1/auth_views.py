import requests
from django.shortcuts import redirect
from django.views.generic import FormView
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import ResetPasswordProxyForm


class ActivateUserAPIView(APIView):
    def get(self, request, uid, token, *args, **kwargs):
        payload = {'uid': uid, 'token': token}

        url = "http://0.0.0.0:8000/api/v1/auth/users/activation/"
        response = requests.post(url, data=payload)

        if response.status_code == 204:
            return Response({}, response.status_code)
        else:
            return Response(response.json())


class PasswordResetFormView(FormView):
    form_class = ResetPasswordProxyForm
    template_name = 'accounts/new_password_set.html'
    extra_context = {'title': 'Password reset', 'button_label': 'Change my password'}

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        response = self._make_resend(form)
        if response.status_code == 204:
            return redirect('main')
        else:
            form.add_error(None, "Password failed validation. Please, choose another one.")
            return self.form_invalid(form)

    def _make_resend(self, form):
        payload = {
            'uid': self.kwargs.get('uid'),
            'token': self.kwargs.get('token'),
            'new_password': form.cleaned_data.get('new_password1'),
            're_new_password': form.cleaned_data.get('new_password2'),
        }

        url = "http://0.0.0.0:8000/api/v1/auth/users/reset_password_confirm/"
        return requests.post(url, data=payload)
