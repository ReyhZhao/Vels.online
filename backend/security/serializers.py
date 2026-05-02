from rest_framework import serializers

from .models import Download, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "wazuh_group"]
        read_only_fields = ["id", "slug", "wazuh_group"]


class AgentSerializer(serializers.Serializer):
    id = serializers.CharField(allow_null=True)
    name = serializers.CharField(allow_null=True)
    ip = serializers.CharField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    os = serializers.CharField(allow_null=True)
    last_seen = serializers.CharField(allow_null=True)


class EventSerializer(serializers.Serializer):
    timestamp = serializers.CharField(allow_null=True)
    rule_description = serializers.CharField()
    rule_id = serializers.CharField()
    level = serializers.IntegerField()
    severity = serializers.CharField()
    agent_name = serializers.CharField()


class PaginatedEventsSerializer(serializers.Serializer):
    events = EventSerializer(many=True)
    total = serializers.IntegerField()


class VulnerabilitySerializer(serializers.Serializer):
    cve = serializers.CharField()
    package = serializers.CharField()
    version = serializers.CharField()
    severity = serializers.CharField()
    fix_available = serializers.BooleanField()


class PaginatedVulnerabilitiesSerializer(serializers.Serializer):
    vulnerabilities = VulnerabilitySerializer(many=True)
    total = serializers.IntegerField()


class EnrollmentSerializer(serializers.Serializer):
    wazuh_group = serializers.CharField()
    manager_host = serializers.CharField()
    install_command = serializers.CharField()


class DownloadSerializer(serializers.ModelSerializer):
    organization_slug = serializers.SlugRelatedField(
        source="organization", slug_field="slug", read_only=True
    )
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Download
        fields = ["id", "label", "platform", "category", "organization_slug", "has_file"]

    def get_has_file(self, obj):
        return bool(obj.s3_key)


class DownloadCreateSerializer(serializers.Serializer):
    label = serializers.CharField()
    platform = serializers.ChoiceField(choices=Download.PLATFORM_CHOICES)
    category = serializers.ChoiceField(choices=Download.CATEGORY_CHOICES)
    organization_slug = serializers.CharField(required=False, allow_blank=True, default="")
