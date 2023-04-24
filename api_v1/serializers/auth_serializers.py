from djoser.serializers import UserSerializer
from rest_framework import serializers

from accounts.models import User
from .mixins import UserMixin


class CustomUserSerializer(UserMixin, UserSerializer):
    uploaded_avatar = serializers.ImageField(use_url=False, write_only=True)
    delete_avatar = serializers.BooleanField(write_only=True, required=False)
    avatar_url = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        addition_fields = (
            'uploaded_avatar',
            'avatar_url',
            'about',
            'facebook',
            'instagram',
            'telegram',
            'whatsapp',
            'delete_avatar',
        )
        fields = UserSerializer.Meta.fields + addition_fields

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

        if validated_data.get('delete_avatar', False) and instance.avatar:
            instance.avatar.delete()
        if not validated_data.get('delete_avatar', False) and avatar:
            instance.avatar.delete()
            instance.avatar = avatar
            instance.save()

        return instance

    @staticmethod
    def _pop_uploaded_avatar(validated_data):
        try:
            return validated_data.pop('uploaded_avatar')
        except KeyError:
            return


class AnotherUserSerializer(UserMixin, serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'username',
            'avatar_url',
            'about',
            'facebook',
            'instagram',
            'telegram',
            'whatsapp',
        )
