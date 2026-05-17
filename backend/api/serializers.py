from rest_framework import serializers


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    is_staff = serializers.BooleanField()
    default_org_slug = serializers.SerializerMethodField()

    def get_default_org_slug(self, obj):
        try:
            org = obj.profile.default_org
            return org.slug if org else None
        except Exception:
            return None
