from django.urls import path

from .views import *

urlpatterns = [
    path('my_albums', AlbumsRecognitionView.as_view(), name='recognition_main'),
    path('process_album/<slug:album_slug>', AlbumProcessingConfirmView.as_view(), name='processing_album_confirm'),
    path('process_album/<slug:album_slug>/find_faces', find_faces_view, name='find_faces'),
    path('process_album/<slug:album_slug>/waiting_frames', AlbumFramesWaitingView.as_view(), name='frames_waiting'),
    path('process_album/<slug:album_slug>/verify_frames/<slug:photo_slug>',
         AlbumVerifyFramesView.as_view(), name='verify_frames'),
    path('process_album/<slug:album_slug>/waiting_patterns',
         AlbumPatternsWaitingView.as_view(), name='patterns_waiting'),
    path('process_album/<slug:album_slug>/verify_patterns', AlbumVerifyPatternsView.as_view(), name='verify_patterns'),
    path('process_album/<slug:album_slug>/group_patterns', AlbumGroupPatternsView.as_view(), name='group_patterns'),
]
