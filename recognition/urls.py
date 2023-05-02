from django.urls import path

from .views import *

urlpatterns = [
    path('photo-with-framed-faces/', return_photo_with_framed_faces, name='photo_with_framed_faces'),
    path('face-img/', return_face_image_view, name='get_face_img'),
    path('my-albums/', AlbumsRecognitionView.as_view(), name='recognition_albums'),
    path('process-album/<slug:album_slug>/confirmation/', AlbumProcessingConfirmView.as_view(),
         name='processing_album_confirm'),
    path('process-album/find-faces/', find_faces_view, name='find_faces'),
    path('process-album/<slug:album_slug>/frames-waiting/', AlbumFramesWaitingView.as_view(), name='frames_waiting'),
    path('process-album/<slug:album_slug>/verify-frames/<slug:photo_slug>/',
         AlbumVerifyFramesView.as_view(), name='verify_frames'),
    path('process-album/<slug:album_slug>/waiting-patterns/',
         AlbumPatternsWaitingView.as_view(), name='patterns_waiting'),
    path('process-album/<slug:album_slug>/verify-patterns/', AlbumVerifyPatternsView.as_view(), name='verify_patterns'),
    path('process-album/<slug:album_slug>/group-patterns/', AlbumGroupPatternsView.as_view(), name='group_patterns'),
    path('process-album/<slug:album_slug>/waiting-for-people-compare/',
         ComparingAlbumPeopleWaitingView.as_view(), name='people_waiting'),
    path('process-album/<slug:album_slug>/verify-tech-matches/',
         VerifyTechPeopleMatchesView.as_view(), name='verify_matches'),
    path('process-album/<slug:album_slug>/manual-matching/',
         ManualMatchingPeopleView.as_view(), name='manual_matching'),
    path('process-album/<slug:album_slug>/save-waiting/',
         AlbumRecognitionDataSavingWaitingView.as_view(), name='save_waiting'),
    path('process-album/<slug:album_slug>/no-faces/', NoFacesAlbumView.as_view(), name='no_faces'),
    path('process-album/<slug:album_slug>/rename-people/', RenameAlbumsPeopleView.as_view(), name='rename_people'),
    path('recognized-people/', RecognizedPeopleView.as_view(), name='recognition_main'),
    path('person/<slug:person_slug>/', RecognizedPersonView.as_view(), name='person'),
    path('find-people/', find_people_view, name='find_people'),
    path('people-search/', SearchPeopleView.as_view(), name='search_people'),
]
