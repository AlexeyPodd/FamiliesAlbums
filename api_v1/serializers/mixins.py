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
