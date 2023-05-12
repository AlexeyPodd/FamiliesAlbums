from rest_framework.serializers import ValidationError

from mainapp.models import Albums


class AlbumMiniatureMixin:
    def get_miniature_url(self, album):
        if album.miniature is None:
            return
        miniature_url = album.miniature.original.url
        request = self.context.get('request')
        return request.build_absolute_uri(miniature_url)


class AlbumsMixin(AlbumMiniatureMixin):
    class Meta:
        model = Albums
        fields = (
            'title',
            'date_start',
            'date_end',
            'location',
            'miniature_url',
            'owner_profile',
            'slug',
        )

    def get_owner_profile(self, album):
        if self.context['request'].user == album.owner:
            return self.context['request'].build_absolute_uri('/api/v1/auth/users/me/')
        else:
            return self.context['request'].build_absolute_uri(
                f'/api/v1/auth/users/profile/{album.owner.username_slug}/',
            )


class UserMixin:
    def get_avatar_url(self, user):
        if not user.avatar:
            return
        avatar_url = user.avatar.url
        request = self.context.get('request')
        return request.build_absolute_uri(avatar_url)


class AlbumProcessingMixin:
    def __init__(self, *args, **kwargs):
        data_collector = kwargs.pop('data_collector')
        self.album_pk = data_collector.album_pk
        self.actual_stage = data_collector.stage
        self.status = data_collector.status
        self.finished_status = data_collector.finished
        self._check_relevance()
        super().__init__(*args, **kwargs)

    def _check_relevance(self):
        if self.finished_status:
            raise ValidationError('Processing of album was finished')

        if self.status is None:
            raise ValidationError('This album is not processing now')

        if self.status != 'completed':
            raise ValidationError('Processing should be completed before receiving next stage data')

        if self.stage != self.actual_stage + 1:
            raise ValidationError('received data does not correspond to the current stage of recognition')
