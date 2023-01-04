from django.urls import path

from .views import *

urlpatterns = [
    path('my_albums', AlbumsRecognitionView.as_view(), name='recognition_main'),
    path('process_album/<slug:album_slug>', AlbumProcessingConfirmView.as_view(), name='processing_album_confirm'),
    path('process_album/<slug:album_slug>/0', zero_stage_album_processing_view, name='zero_stage_album_processing')
]
