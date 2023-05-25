from django.test import SimpleTestCase
from django.urls import reverse, resolve

from recognition.views import return_photo_with_framed_faces, SearchPeopleView, find_people_view, RecognizedPersonView,\
    RecognizedPeopleView, RenameAlbumsPeopleView, NoFacesAlbumView, AlbumRecognitionDataSavingWaitingView, \
    ManualMatchingPeopleView, VerifyTechPeopleMatchesView, ComparingAlbumPeopleWaitingView, AlbumGroupPatternsView, \
    AlbumVerifyPatternsView, AlbumPatternsWaitingView, AlbumVerifyFramesView, AlbumFramesWaitingView, find_faces_view, \
    AlbumProcessingConfirmView, AlbumsRecognitionView, return_face_image_view


class TestUrls(SimpleTestCase):
    def test_photo_with_framed_faces_url_is_resolves(self):
        url = reverse('photo_with_framed_faces')
        self.assertEqual(resolve(url).func, return_photo_with_framed_faces)

    def test_get_face_img_url_is_resolves(self):
        url = reverse('get_face_img')
        self.assertEqual(resolve(url).func, return_face_image_view)

    def test_recognition_albums_url_is_resolves(self):
        url = reverse('recognition_albums')
        self.assertEqual(resolve(url).func.view_class, AlbumsRecognitionView)

    def test_processing_album_confirm_url_is_resolves(self):
        url = reverse('processing_album_confirm', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumProcessingConfirmView)

    def test_find_faces_url_is_resolves(self):
        url = reverse('find_faces')
        self.assertEqual(resolve(url).func, find_faces_view)

    def test_frames_waiting_url_is_resolves(self):
        url = reverse('frames_waiting', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumFramesWaitingView)

    def test_verify_frames_url_is_resolves(self):
        url = reverse('verify_frames', kwargs={'album_slug': 'some-album-slug',
                                               'photo_slug': 'some-photo-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumVerifyFramesView)

    def test_patterns_waiting_url_is_resolves(self):
        url = reverse('patterns_waiting', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumPatternsWaitingView)

    def test_verify_patterns_url_is_resolves(self):
        url = reverse('verify_patterns', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumVerifyPatternsView)

    def test_group_patterns_url_is_resolves(self):
        url = reverse('group_patterns', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumGroupPatternsView)

    def test_people_waiting_url_is_resolves(self):
        url = reverse('people_waiting', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, ComparingAlbumPeopleWaitingView)

    def test_verify_matches_url_is_resolves(self):
        url = reverse('verify_matches', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, VerifyTechPeopleMatchesView)

    def test_manual_matching_url_is_resolves(self):
        url = reverse('manual_matching', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, ManualMatchingPeopleView)

    def test_save_waiting_url_is_resolves(self):
        url = reverse('save_waiting', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, AlbumRecognitionDataSavingWaitingView)

    def test_no_faces_url_is_resolves(self):
        url = reverse('no_faces', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, NoFacesAlbumView)

    def test_rename_people_url_is_resolves(self):
        url = reverse('rename_people', kwargs={'album_slug': 'some-album-slug'})
        self.assertEqual(resolve(url).func.view_class, RenameAlbumsPeopleView)

    def test_recognition_main_url_is_resolves(self):
        url = reverse('recognition_main')
        self.assertEqual(resolve(url).func.view_class, RecognizedPeopleView)

    def test_person_url_is_resolves(self):
        url = reverse('person', kwargs={'person_slug': 'some-person-slug'})
        self.assertEqual(resolve(url).func.view_class, RecognizedPersonView)

    def test_find_people_url_is_resolves(self):
        url = reverse('find_people')
        self.assertEqual(resolve(url).func, find_people_view)

    def test_search_people_url_is_resolves(self):
        url = reverse('search_people')
        self.assertEqual(resolve(url).func.view_class, SearchPeopleView)
