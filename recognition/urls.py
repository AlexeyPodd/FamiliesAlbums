from django.urls import path

from .views import *

urlpatterns = [
    path('', MainRecognitionView.as_view(), name='recognition_main'),
]
