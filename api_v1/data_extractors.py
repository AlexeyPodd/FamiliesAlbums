from rest_framework.reverse import reverse

from mainapp.models import Photos
from recognition.models import People
from recognition.redis_interface.functional_api import RedisAPIPhotoSlug, RedisAPIPhotoDataGetter, \
    RedisAPIAlbumDataGetter, RedisAPIMatchesGetter, RedisAPIProcessedPhotos


class DataExtractor:
    completed_stage = None

    def __init__(self, album_pk, request):
        if self.completed_stage is None:
            raise NotImplementedError
        self.album_pk = album_pk
        self.request = request

    def get_data(self):
        raise NotImplementedError


class ProcessedPhotosAmountExtractor(DataExtractor):
    completed_stage = 0

    def get_data(self):
        processed = RedisAPIProcessedPhotos.get_processed_photos_amount(self.album_pk)
        total = Photos.objects.filter(album_id=self.album_pk, is_private=False).count()
        data = {"total_photos_amount": total, "processed_photos_amount": processed}
        return data


class FacesInPhotosExtractor(DataExtractor):
    completed_stage = 1

    def get_data(self):
        photo_slugs = RedisAPIPhotoSlug.get_photo_slugs(self.album_pk)
        image_links = [reverse('api_v1:photo-with-frames', request=self.request) + '?photo=' + photo_slug
                       for photo_slug in photo_slugs]

        photos = Photos.objects.filter(slug__in=photo_slugs)
        faces_amounts = [RedisAPIPhotoDataGetter.get_faces_amount_in_photo(photo_pk=photos.get(slug=photo_slug).pk)
                         for photo_slug in photo_slugs]
        data = [{'photo_slug': photo_slugs[i], 'image': image_links[i], 'faces_amount': faces_amounts[i]}
                for i in range(len(photo_slugs))]
        return data


class PatternsFacesExtractor(DataExtractor):
    completed_stage = 3

    def get_data(self):
        patterns_amounts = RedisAPIAlbumDataGetter.get_album_faces_amounts(self.album_pk)
        data = []
        for i, faces_amount in enumerate(patterns_amounts, 1):
            pattern_faces = []
            for j in range(1, faces_amount + 1):
                face_name = f'face_{j}'
                face_image_link = self.request.\
                    build_absolute_uri(f"/media/temp_photos/album_{self.album_pk}/patterns/{i}/{j}.jpg")
                pattern_faces.append({'face_name': face_name, 'image': face_image_link})

            data.append({'pattern_name': f'pattern_{i}', 'faces': pattern_faces})
        return data


class PatternsForGroupingExtractor(DataExtractor):
    completed_stage = 4

    def get_data(self):
        patterns_amount = len(RedisAPIAlbumDataGetter.get_album_faces_amounts(self.album_pk))

        data = []
        for i in range(1, patterns_amount+1):
            patterns_image_link = self.request.\
                build_absolute_uri(f"/media/temp_photos/album_{self.album_pk}/patterns/{i}/1.jpg")

            data.append({'pattern_name': f'pattern_{i}', 'image': patterns_image_link})

        return data


class TechPairsExtractor(DataExtractor):
    completed_stage = 6

    def get_data(self):
        old_people_pks, new_people_inds = RedisAPIMatchesGetter.get_matching_people(self.album_pk)

        # Getting urls of first faces of first patterns of each person
        # new people
        patt_inds = RedisAPIAlbumDataGetter.get_first_patterns_indexes_of_people(self.album_pk, new_people_inds)
        new_face_urls = [self.request.build_absolute_uri(f"/media/temp_photos/album_{self.album_pk}/patterns/{x}/1.jpg")
                         for x in patt_inds]

        # old people
        old_people = People.objects.filter(pk__in=old_people_pks).prefetch_related('patterns_set__faces_set')
        old_face_urls = [reverse('api_v1:face-img', request=self.request) + '?face=' +
                         old_people.get(pk=x).patterns_set.first().faces_set.first().slug for x in old_people_pks]

        data = {}
        for i in range(len(new_people_inds)):
            new_person_data = {'name': f'person_{new_people_inds[i]}', 'image': new_face_urls[i]}
            old_person_data = {'pk': old_people_pks[i], 'image': old_face_urls[i]}
            data.update({f'pair_{i+1}': {'new_person': new_person_data, 'old_person': old_person_data}})

        return data


class SinglePeopleExtractor(DataExtractor):
    completed_stage = 7

    def get_data(self):
        new_people = RedisAPIMatchesGetter.get_new_unpaired_people(self.album_pk)
        old_people = self._get_old_unpaired_people()

        new_people_data = [{'name': f'person_{ind}', 'image': self.request.build_absolute_uri(img_url)}
                           for ind, img_url in new_people]
        old_people_data = [{'pk': pk, 'image': img_url} for pk, img_url in old_people]
        data = {'new_people': new_people_data, 'old_people': old_people_data}
        return data

    def _get_old_unpaired_people(self):
        queryset = People.objects.prefetch_related('patterns_set__faces_set').filter(owner=self.request.user)

        # Collecting already paired people with created people of this album
        paired = RedisAPIMatchesGetter.get_old_paired_people(self.album_pk)

        # Taking face image url of one of the faces of person,
        # if it is not already paired with one of people from this album
        old_ppl = []
        for person in queryset:
            if person.pk not in paired:
                old_ppl.append((person.pk,
                                reverse('api_v1:face-img', request=self.request) + '?face=' +
                                person.patterns_set.first().faces_set.first().slug))

        return old_ppl
