from rest_framework import serializers

from .models import Download, Organization, WorkPackage, WorkPackageItem


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
    id = serializers.CharField()
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
    id = serializers.CharField()
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


class FleetVulnStatsSerializer(serializers.Serializer):
    critical = serializers.IntegerField()
    high = serializers.IntegerField()
    medium = serializers.IntegerField()
    low = serializers.IntegerField()
    affected_systems = serializers.IntegerField()
    fixable = serializers.IntegerField()


class FleetVulnerabilitySerializer(serializers.Serializer):
    cve = serializers.CharField()
    severity = serializers.CharField()
    cvss_score = serializers.FloatField(allow_null=True)
    package = serializers.CharField()
    affected_agents = serializers.IntegerField()
    fix_available = serializers.BooleanField()
    published = serializers.CharField(allow_null=True)


class FleetVulnerabilitiesResponseSerializer(serializers.Serializer):
    vulnerabilities = FleetVulnerabilitySerializer(many=True)
    total = serializers.IntegerField()
    stats = FleetVulnStatsSerializer()


class FleetEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    timestamp = serializers.CharField(allow_null=True)
    rule_description = serializers.CharField()
    rule_id = serializers.CharField()
    level = serializers.IntegerField()
    severity = serializers.CharField()
    agent_id = serializers.CharField()
    agent_name = serializers.CharField()


class FleetEventStatsSerializer(serializers.Serializer):
    critical = serializers.IntegerField()
    high = serializers.IntegerField()
    medium = serializers.IntegerField()
    low = serializers.IntegerField()
    total = serializers.IntegerField()
    events_24h = serializers.IntegerField()


class FleetEventsResponseSerializer(serializers.Serializer):
    events = FleetEventSerializer(many=True)
    total = serializers.IntegerField()
    stats = FleetEventStatsSerializer()


class VulnerabilitySnapshotSerializer(serializers.Serializer):
    date = serializers.DateField()
    critical = serializers.IntegerField()
    high = serializers.IntegerField()
    medium = serializers.IntegerField()
    low = serializers.IntegerField()
    new_count = serializers.IntegerField()
    resolved_count = serializers.IntegerField()


class CveAffectedAgentSerializer(serializers.Serializer):
    agent_id = serializers.CharField()
    agent_name = serializers.CharField()
    installed_version = serializers.CharField(allow_null=True)
    fixed_version = serializers.CharField(allow_null=True)
    fix_available = serializers.BooleanField()


class CveDetailSerializer(serializers.Serializer):
    cve = serializers.CharField()
    severity = serializers.CharField()
    cvss_score = serializers.FloatField(allow_null=True)
    package = serializers.CharField()
    description = serializers.CharField()
    published = serializers.CharField(allow_null=True)
    references = serializers.ListField(child=serializers.CharField(), required=False)
    affected_agents = CveAffectedAgentSerializer(many=True)


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


class WorkPackageItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkPackageItem
        fields = [
            "id", "cve_id", "severity", "cvss_score", "description",
            "references", "affected_agent_count", "impact_score",
            "affected_agents", "status", "note",
        ]


class WorkPackageSerializer(serializers.ModelSerializer):
    items = WorkPackageItemSerializer(many=True, read_only=True)
    generated_by = serializers.StringRelatedField()

    class Meta:
        model = WorkPackage
        fields = ["id", "created_at", "generated_by", "items"]
