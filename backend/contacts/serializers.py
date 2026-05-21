from rest_framework import serializers
from .models import Contact


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "name", "email", "job_title", "department", "created_at"]
        read_only_fields = ["id", "created_at"]


class ContactCreateSerializer(serializers.ModelSerializer):
    org = serializers.CharField(write_only=True)

    class Meta:
        model = Contact
        fields = ["org", "name", "email", "job_title", "department"]

    def validate(self, attrs):
        from security.models import Organization
        org_slug = attrs.pop("org")
        try:
            attrs["organisation"] = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            raise serializers.ValidationError({"org": "Organisation not found."})
        return attrs

    def create(self, validated_data):
        return Contact.objects.create(**validated_data)


class ContactPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["name", "email", "job_title", "department"]
