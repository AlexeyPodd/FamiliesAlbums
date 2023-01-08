from django.urls import path

from .views import *

urlpatterns = [
    path('my_albums', AlbumsRecognitionView.as_view(), name='recognition_main'),
    path('process_album/<slug:album_slug>', AlbumProcessingConfirmView.as_view(), name='processing_album_confirm'),
    path('process_album/<slug:album_slug>/0', zero_stage_album_processing_view, name='zero_stage_album_processing'),
    path('process_album/<slug:album_slug>/waiting', AlbumProcessWaitingView.as_view(), name='process_waiting'),
    path('process_album/<slug:album_slug>/verify_frames/<slug:photo_slug>',
         AlbumVerifyFramesView.as_view(), name='verify_frames'),
]
