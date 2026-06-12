from rest_framework import serializers

from security.models import Organization
from .models import Hunt, HuntEvent, HuntFinding


class HuntEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = HuntEvent
        fields = ["seq", "turn", "type", "data", "created_at"]


class HuntFindingSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    materialised_incident_display_id = serializers.CharField(
        source="materialised_incident.display_id", read_only=True, default=None,
    )

    class Meta:
        model = HuntFinding
        fields = [
            "id", "organization", "organization_name", "lens", "source_index",
            "wazuh_doc_id", "summary", "materialised_incident_display_id", "created_at",
        ]


class HuntListSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True, default=None)
    finding_count = serializers.SerializerMethodField()
    spawned_incident_count = serializers.SerializerMethodField()

    class Meta:
        model = Hunt
        fields = [
            "id", "title", "seed_kind", "status", "scope_all_orgs", "lookback_days",
            "owner_username", "finding_count", "spawned_incident_count",
            "created_at", "updated_at",
        ]

    def get_finding_count(self, obj):
        return obj.findings.count()

    def get_spawned_incident_count(self, obj):
        return (
            obj.findings.filter(materialised_incident__isnull=False)
            .values("materialised_incident").distinct().count()
        )


class HuntDetailSerializer(HuntListSerializer):
    scope_org_ids = serializers.SerializerMethodField()
    events = HuntEventSerializer(many=True, read_only=True)
    findings = HuntFindingSerializer(many=True, read_only=True)
    proposed_incidents = serializers.SerializerMethodField()

    class Meta(HuntListSerializer.Meta):
        fields = HuntListSerializer.Meta.fields + [
            "seed_text", "seed_url", "scope_org_ids", "cancel_requested",
            "events", "findings", "proposed_incidents",
        ]

    def get_scope_org_ids(self, obj):
        return list(obj.scope_orgs.values_list("id", flat=True))

    def get_proposed_incidents(self, obj):
        from .grouping import proposed_incidents
        return proposed_incidents(obj)


class HuntCreateSerializer(serializers.Serializer):
    seed_kind = serializers.ChoiceField(choices=Hunt.SEED_CHOICES, default=Hunt.SEED_QUESTION)
    seed_text = serializers.CharField(required=False, allow_blank=True, default="")
    seed_url = serializers.URLField(required=False, allow_blank=True, default="")
    scope_all_orgs = serializers.BooleanField(default=True)
    scope_org_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
    )
    lookback_days = serializers.IntegerField(min_value=1, max_value=365, default=30)

    def validate(self, attrs):
        if attrs["seed_kind"] == Hunt.SEED_QUESTION and not attrs.get("seed_text"):
            raise serializers.ValidationError("seed_text is required for a question seed.")
        if attrs["seed_kind"] == Hunt.SEED_URL and not attrs.get("seed_url"):
            raise serializers.ValidationError("seed_url is required for a URL seed.")
        if not attrs["scope_all_orgs"] and not attrs.get("scope_org_ids"):
            raise serializers.ValidationError(
                "Select at least one organisation when scope_all_orgs is false."
            )
        return attrs
