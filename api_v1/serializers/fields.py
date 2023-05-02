from rest_framework import serializers


class MiniatureSlugRelatedField(serializers.SlugRelatedField):
    def get_queryset(self):
        view = self.context.get('view')
        request = self.context.get('request')
        queryset = super().get_queryset()

        if not request or not view or not queryset:
            return

        if request.method == 'POST':
            return

        return queryset.filter(album__slug=view.kwargs.get('album_slug'))


class DataOutputField(serializers.Field):
    def to_representation(self, value):
        pass
