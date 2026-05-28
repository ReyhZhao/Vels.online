from rest_framework import serializers
from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    incident_display_id = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source='organization.slug', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'display_id', 'title', 'severity', 'state',
            'source_kind', 'source_ref', 'incident', 'incident_display_id',
            'acknowledged_by', 'acknowledged_at', 'created_at', 'updated_at',
            'org_slug',
        ]
        read_only_fields = [
            'id', 'display_id', 'title', 'severity', 'source_kind', 'source_ref',
            'created_at', 'updated_at', 'org_slug',
        ]

    def get_incident_display_id(self, obj):
        return obj.incident.display_id if obj.incident_id else None


class AlertIngestSerializer(serializers.ModelSerializer):
    """Used only by the ingest endpoint — accepts all writable fields."""

    class Meta:
        model = Alert
        fields = [
            'source_kind', 'source_ref', 'title', 'severity',
        ]
