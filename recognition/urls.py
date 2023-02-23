from django.urls import path

from .views import *

urlpatterns = [
    path('photo_with_framed_faces/<slug:photo_slug>', return_photo_with_framed_faces, name='photo_with_framed_faces'),
    path('face_img/<slug:face_slug>/', return_face_image_view, name='get_face_img'),
    path('my_albums/', AlbumsRecognitionView.as_view(), name='recognition_albums'),
    path('process_album/<slug:album_slug>/', AlbumProcessingConfirmView.as_view(), name='processing_album_confirm'),
    path('process_album/<slug:album_slug>/find_faces/', find_faces_view, name='find_faces'),
    path('process_album/<slug:album_slug>/frames_waiting/', AlbumFramesWaitingView.as_view(), name='frames_waiting'),
    path('process_album/<slug:album_slug>/verify_frames/<slug:photo_slug>/',
         AlbumVerifyFramesView.as_view(), name='verify_frames'),
    path('process_album/<slug:album_slug>/waiting_patterns/',
         AlbumPatternsWaitingView.as_view(), name='patterns_waiting'),
    path('process_album/<slug:album_slug>/verify_patterns/', AlbumVerifyPatternsView.as_view(), name='verify_patterns'),
    path('process_album/<slug:album_slug>/group_patterns/', AlbumGroupPatternsView.as_view(), name='group_patterns'),
    path('process_album/<slug:album_slug>/waiting_for_people_compare/',
         ComparingAlbumPeopleWaitingView.as_view(), name='people_waiting'),
    path('process_album/<slug:album_slug>/verify_tech_matches/',
         VerifyTechPeopleMatchesView.as_view(), name='verify_matches'),
    path('process_album/<slug:album_slug>/manual_matching/',
         ManualMatchingPeopleView.as_view(), name='manual_matching'),
    path('process_album/<slug:album_slug>/save_waiting/',
         AlbumRecognitionDataSavingWaitingView.as_view(), name='save_waiting'),
    path('process_album/<slug:album_slug>/no_faces/', NoFacesAlbumView.as_view(), name='no_faces'),
    path('recognized_people/', RecognizedPeopleView.as_view(), name='recognition_main'),
    path('person/<slug:person_slug>/', RecognizedPersonView.as_view(), name='person'),
    path('people_search/', SearchPeopleView.as_view(), name='search_people'),
]
