import os

from PIL import Image, ImageDraw, ImageFont
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from mainapp.utils import delete_from_favorites
from photoalbums.settings import BASE_DIR
from recognition.models import People, Faces
from recognition.tasks import recognition_task
from recognition.redis_interface.functional_api import RedisAPIPhotoDataGetter, RedisAPISearchGetter, \
    RedisAPISearchChecker, RedisAPISearchSetter
from .data_collectors import RecognitionStateCollector
from .managers import StartProcessingManager, VerifyFramesManager, VerifyPatternsManager, GroupPatternsManager, \
    VerifyTechPeopleMatchesManager, ManualMatchingPeopleManager
from .permissions import AlbumsPermission, PhotosPermission, IsOwner
from .serializers.auth_serializers import AnotherUserSerializer
from .serializers.rec_processing_serializers import AlbumProcessingInfoSerializer, StartAlbumProcessingSerializer, \
    VerifyFramesSerializer, VerifyPatternsSerializer, GroupPatternsSerializer, VerifyTechPeopleMatchesSerializer, \
    ManualMatchingPeopleSerializer
from .serializers.serializers import MainPageSerializer, AlbumsListSerializer, AlbumPostAndDetailSerializer, \
    PhotoDetailSerializer, PhotosListSerializer, PeopleListSerializer, PersonSerializer, RecognitionAlbumsSerializer, \
    FoundedPeopleSerializer, SearchStartOverSerializer
from mainapp.models import Albums, Photos
from mainapp.tasks import album_deletion_task
from .utils import set_random_album_cover


class AnotherUserDetailAPIView(RetrieveAPIView):
    serializer_class = AnotherUserSerializer
    queryset = User.objects.all()
    lookup_field = 'username_slug'


class MainPageAPIView(ListAPIView):
    serializer_class = MainPageSerializer

    def get_queryset(self):
        return Albums.objects.filter(
            is_private=False,
            photos__isnull=False,
        ).annotate(
            photos_amount=Count('photos'),
        ).order_by(
            '-time_create',
        )[:16]


class AlbumsViewSet(ModelViewSet):
    permission_classes = (AlbumsPermission,)
    lookup_field = 'slug'
    lookup_url_kwarg = 'album_slug'

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            return Albums.objects.filter(owner__username_slug=self.kwargs.get('username_slug')).annotate(
                photos_amount=Count('photos'),
            ).prefetch_related(
                Prefetch('photos_set', to_attr='filtered_photos_set')
            )
        else:
            return Albums.objects.filter(
                owner__username_slug=self.kwargs.get('username_slug'),
                is_private=False,
            ).annotate(
                photos_amount=Count('photos'),
            ).prefetch_related(
                Prefetch('photos_set', queryset=Photos.objects.filter(is_private=False), to_attr='filtered_photos_set'),
            )

    def get_serializer_class(self):
        if self.detail or self.request.method == 'POST':
            return AlbumPostAndDetailSerializer
        else:
            return AlbumsListSerializer

    def perform_destroy(self, instance):
        album_deletion_task.delay(instance.pk)


class PhotoAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = (PhotosPermission,)
    serializer_class = PhotoDetailSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'photo_slug'

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.username_slug == self.kwargs.get('username_slug'):
            return Photos.objects.filter(album__slug=self.kwargs.get('album_slug'))
        else:
            return Photos.objects.filter(
                album__slug=self.kwargs.get('album_slug'),
                is_private=False,
            )

    def perform_destroy(self, instance):
        album = instance.album
        need_cover = album.miniature == instance
        super().perform_destroy(instance)
        if need_cover:
            set_random_album_cover(album)


class FavoritesAlbumsViewSet(ModelViewSet):
    lookup_field = 'slug'
    lookup_url_kwarg = 'album_slug'
    serializer_class = AlbumsListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Albums.objects.filter(in_users_favorites=self.request.user)

    def create(self, request, *args, **kwargs):
        album_slug = request.data.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."})

        if album.owner == request.user:
            return Response({"error": "You can add to favorites only someone else's albums."})

        if album.is_private:
            return Response({"error": "Album not found."})

        if album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "This album is already in your favorites."})

        album.in_users_favorites.add(request.user)
        album.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        album_slug = kwargs.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug, is_private=False)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."})

        if not album.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "Album is not in your favorites."})

        delete_from_favorites(request.user, album)

        album.pk, album.id = None, None
        album._state.adding = True
        album.owner = request.user
        album.miniature = None
        album.save()

        for photo in Photos.objects.filter(album__slug=album_slug, is_private=False):
            photo.pk, photo.id = None, None
            photo.faces_extracted = False
            photo._state.adding = True
            photo.album = album
            photo.save()

        album.miniature = Photos.objects.get(original=Albums.objects.get(slug=album_slug).miniature.original,
                                             album=album)
        album.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        delete_from_favorites(self.request.user, instance)


class FavoritesPhotosViewSet(ModelViewSet):
    lookup_field = 'slug'
    lookup_url_kwarg = 'photo_slug'
    serializer_class = PhotosListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Photos.objects.filter(in_users_favorites=self.request.user)

    def create(self, request, *args, **kwargs):
        photo_slug = request.data.get('photo_slug')

        if photo_slug is None:
            return Response({"error": "Photo slug was not specified."})

        try:
            photo = Photos.objects.get(slug=photo_slug)
        except ObjectDoesNotExist:
            return Response({"error": "Photo not found."})

        if photo.album.owner == request.user:
            return Response({"error": "You can add to favorites only someone else's photo."})

        if photo.is_private:
            return Response({"error": "Photo not found."})

        if photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "This photo is already in your favorites."})

        photo.in_users_favorites.add(request.user)
        photo.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        photo_slug = kwargs.get('photo_slug')

        # Checking photo
        if photo_slug is None:
            return Response({"error": "Photo slug was not specified."})

        try:
            photo = Photos.objects.get(slug=photo_slug, is_private=False)
        except ObjectDoesNotExist:
            return Response({"error": "Photo not found."})

        if not photo.in_users_favorites.filter(username_slug=request.user.username_slug).exists():
            return Response({"error": "Photo is not in your favorites."})

        # Checking album
        album_slug = request.data.get('album_slug')

        if album_slug is None:
            return Response({"error": "Album slug was not specified."})

        try:
            album = Albums.objects.get(slug=album_slug)
        except ObjectDoesNotExist:
            return Response({"error": "You don't have album with this slug."})

        if album.owner != request.user:
            return Response({"error": "You don't have album with this slug."})

        # Checking photo in album
        if Photos.objects.filter(album_id=album.pk, original=photo.original).exists():
            return Response({"error": "You already have this photo in specified album."})

        delete_from_favorites(request.user, photo)

        photo.pk, photo.id = None, None
        photo.faces_extracted = False
        photo._state.adding = True
        photo.album = album
        photo.is_private = album.is_private
        photo.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        delete_from_favorites(self.request.user, instance)


class PeopleViewSet(ModelViewSet):
    lookup_field = 'slug'
    lookup_url_kwarg = 'person_slug'
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        if self.detail:
            return People.objects.filter(owner=self.request.user).annotate(
                patterns_amount=Count('patterns'),
                photos_amount=Count('patterns__faces__photo', distinct=True),
                albums_amount=Count('patterns__faces__photo__album', distinct=True),
            )
        else:
            return People.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.detail:
            return PersonSerializer
        else:
            return PeopleListSerializer


class RecognitionAlbumsListAPIView(ListAPIView):
    serializer_class = RecognitionAlbumsSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Albums.objects.filter(owner=self.request.user).annotate(
            processed_photos_amount=Count('photos', filter=(Q(photos__is_private=False) & Q(photos__faces_extracted=True))),
            public_photos_amount=Count('photos', filter=Q(photos__is_private=False)),
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def return_face_image_view(request):
    face_slug = request.GET.get('face')
    if face_slug is None:
        return Response({"error": "Face slug was not specified."})

    try:
        face = Faces.objects.select_related('photo').get(slug=face_slug)
    except ObjectDoesNotExist:
        return Response({"error": "Face not found."})

    if face.photo.is_private:
        return Response({"error": "Face not found."})

    response = cache.get(face_slug)
    if response:
        return response

    photo_img = Image.open(os.path.join(BASE_DIR, face.photo.original.url[1:]))
    top, right, bottom, left = face.loc_top, face.loc_right, face.loc_bot, face.loc_left
    face_img = photo_img.crop((left, top, right, bottom))
    response = HttpResponse(content_type='image/jpg')
    face_img.save(response, "JPEG")
    cache.set(face_slug, response, 60 * 5)
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def return_photo_with_framed_faces(request):
    photo_slug = request.GET.get('photo')
    if photo_slug is None:
        return Response({"error": "Photo slug was not specified."})

    try:
        photo = Photos.objects.select_related('album__owner').get(slug=photo_slug)
    except ObjectDoesNotExist:
        return Response({"error": "Photo not found."})

    if photo.is_private:
        return Response({"error": "Photo not found."})

    if request.user != photo.album.owner:
        return Response({"error": "You are not owner of this photo."})

    # Loading faces locations from redis
    faces_locations = RedisAPIPhotoDataGetter.get_face_locations_in_photo(photo.pk)

    # Drawing
    image = Image.open(os.path.join(BASE_DIR, photo.original.url[1:]))
    draw = ImageDraw.Draw(image)
    for i, location in enumerate(faces_locations, 1):
        top, right, bottom, left = location
        draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=4)
        fontsize = (bottom - top) // 3
        font = ImageFont.truetype("arialbd.ttf", fontsize)
        draw.text((left, top), str(i), fill=(255, 0, 0), font=font)
    del draw

    response = HttpResponse(content_type='image/jpg')
    image.save(response, "JPEG")
    return response


class AlbumProcessingAPIView(APIView):
    permission_classes = (IsOwner,)
    data_collector_class = RecognitionStateCollector
    manager_classes = {manager_class.recognition_stage: manager_class for manager_class in [
        StartProcessingManager,
        VerifyFramesManager,
        VerifyPatternsManager,
        GroupPatternsManager,
        VerifyTechPeopleMatchesManager,
        ManualMatchingPeopleManager,
    ]}
    # Serializer classes and data keys they expect
    post_serializer_classes = {
        'start': StartAlbumProcessingSerializer,
        'photos_faces': VerifyFramesSerializer,
        'patterns': VerifyPatternsSerializer,
        'people_patterns': GroupPatternsSerializer,
        'verified_pairs': VerifyTechPeopleMatchesSerializer,
        'manual_pairs': ManualMatchingPeopleSerializer,
    }

    def get(self, request, *args, **kwargs):
        try:
            album = self.get_object()
        except ObjectDoesNotExist:
            return Response({'error': 'Album not found'})

        data_collector = self.data_collector_class(album.pk, request=request)
        data_collector.collect()

        serializer = self.get_serializer(instance=data_collector)

        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        try:
            album = self.get_object()
        except ObjectDoesNotExist:
            return Response({'error': 'Album not found'})

        data_collector = self.data_collector_class(album.pk)

        serializer = self.get_serializer(data=request.data, data_collector=data_collector)
        serializer.is_valid(raise_exception=True)

        if 'start' in serializer.validated_data:
            data_collector.data = serializer.validated_data
        else:
            data_collector.data = next(iter(serializer.validated_data.values()))

        manager = self.get_manager(data_collector, user=request.user)
        manager.run()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_object(self):
        obj = Albums.objects.get(slug=self.kwargs['album_slug'])
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer(self, instance=None, data=None, data_collector=None):
        if self.request.method == 'GET':
            if instance is None:
                raise ValidationError("Serializer need instance")
            return AlbumProcessingInfoSerializer(instance)

        if self.request.method == 'POST':
            if data is None or data_collector is None:
                raise ValidationError("Serializer need data to validate and source of stage and status processing")

            serializer_class = self.post_serializer_classes.get(next(iter(data.keys())))
            if serializer_class is None:
                raise ValidationError("Wrong data key. Can't get serializer.")

            return serializer_class(data=data, data_collector=data_collector, context={'user': self.request.user})

    def get_manager(self, data_collector, user):
        next_stage = data_collector.stage + 1 if data_collector.stage else 0
        if isinstance(data_collector.data, dict) and data_collector.data.get('start', False):
            next_stage = 0

        try:
            return self.manager_classes[next_stage](data_collector, user)
        except KeyError:
            raise ValidationError("Invalid stage for getting album process manager.")


class SearchPersonAPIView(APIView):
    permission_classes = (IsOwner,)

    def get(self, request, *args, **kwargs):
        try:
            self._person = self.get_object()
        except ObjectDoesNotExist:
            return Response({'error': 'Person not found'})

        searching_now = RedisAPISearchChecker.is_person_searching(self._person.pk)
        search_completed = bool(RedisAPISearchGetter.get_founded_similar_people(self._person.pk))

        if not searching_now and not search_completed:
            RedisAPISearchSetter.prepare_to_search(self._person.pk)
            recognition_task.delay(self._person.pk, 0)
            return Response(f'Search of people similar to {self._person.slug} started')

        if searching_now:
            processed_patterns_amount = RedisAPISearchGetter.get_searched_patterns_amount(self._person.pk)
            total_patterns_amount = self._person.patterns_set.count()
            return Response({
                'searching_now': True,
                'processed_patterns_amount': processed_patterns_amount,
                'total_patterns_amount': total_patterns_amount,
            })

        if search_completed:
            query_list = self.get_query_list()
            serializer = FoundedPeopleSerializer(query_list, many=True)
            return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        try:
            self._person = self.get_object()
        except ObjectDoesNotExist:
            return Response({'error': 'Person not found'})

        serializer = SearchStartOverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if RedisAPISearchChecker.is_person_searching(self._person.pk):
            return Response({'error': 'Search is running now'})

        RedisAPISearchSetter.prepare_to_search(self._person.pk)
        recognition_task.delay(self._person.pk, 0)
        return Response(f'Search of people similar to {self._person.slug} started')

    def get_object(self):
        person_slug = self.request.query_params.get('person')
        if person_slug is None:
            raise ValidationError("person slug was not specified")
        obj = People.objects.get(slug=person_slug)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_query_list(self):
        nearest_people_pks = RedisAPISearchGetter.get_founded_similar_people(self._person.pk)
        queryset = People.objects.prefetch_related('patterns_set__faces_set').select_related('owner')\
            .filter(pk__in=nearest_people_pks)\
            .annotate(
                photos_amount=Count('patterns__faces__photo', distinct=True),
                albums_amount=Count('patterns__faces__photo__album', distinct=True),
            )
        query_list = sorted(queryset, key=lambda p: nearest_people_pks.index(p.pk))
        return query_list
