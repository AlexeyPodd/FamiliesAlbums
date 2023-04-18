from djoser.serializers import UserSerializer
from rest_framework import serializers


class CustomUserSerializer(UserSerializer):
    uploaded_avatar = serializers.ImageField(use_url=False, write_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        addition_fields = ('uploaded_avatar', 'avatar_url', 'facebook', 'instagram', 'telegram', 'whatsapp')
        fields = UserSerializer.Meta.fields + addition_fields

    def get_avatar_url(self, user):
        if not user.avatar:
            return
        avatar_url = user.avatar.url
        request = self.context.get('request')
        return request.build_absolute_uri(avatar_url)

    def create(self, validated_data):
        avatar = self._pop_uploaded_avatar(validated_data)
        instance = super().create(validated_data)
        if avatar is not None:
            instance.avatar = avatar
            instance.save()
        return instance

    def update(self, instance, validated_data):
        avatar = self._pop_uploaded_avatar(validated_data)
        instance = super().update(instance, validated_data)
        if avatar is not None:
            instance.avatar = avatar
            instance.save()
        return instance

    @staticmethod
    def _pop_uploaded_avatar(validated_data):
        try:
            return validated_data.pop('uploaded_photos')
        except KeyError:
            return
