from rest_framework import serializers


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    is_staff = serializers.BooleanField()
