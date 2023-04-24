from mainapp.models import Albums


class AlbumsMixin:
    class Meta:
        model = Albums
        fields = (
            'title',
            'date_start',
            'date_end',
            'location',
            'miniature_url',
        )

    def get_miniature_url(self, album):
        if album.miniature is None:
            return
        miniature_url = album.miniature.original.url
        request = self.context.get('request')
        return request.build_absolute_uri(miniature_url)


class UserMixin:
    def get_avatar_url(self, user):
        if not user.avatar:
            return
        avatar_url = user.avatar.url
        request = self.context.get('request')
        return request.build_absolute_uri(avatar_url)
