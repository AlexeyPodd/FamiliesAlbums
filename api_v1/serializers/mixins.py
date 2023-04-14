from mainapp.models import Albums


class AlbumsMixin:
    class Meta:
        model = Albums
        fields = (
            'title',
            'date_start',
            'date_end',
            'location',
            'owner',
            'miniature_url',
        )

    def get_miniature_url(self, album):
        miniature_url = album.miniature.original.url
        request = self.context.get('request')
        return request.build_absolute_uri(miniature_url)
