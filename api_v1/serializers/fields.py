from rest_framework import serializers


class MiniaturePrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        view = self.context.get('view')
        request = self.context.get('request')
        queryset = super().get_queryset()

        if not request or not view or not queryset:
            return None

        if request.method == 'POST':
            return None

        return queryset.filter(album_id=int(view.kwargs.get('pk')))
