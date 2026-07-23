from rest_framework import serializers

from .models import CapturedPayload, IngestEndpoint, PayloadElementOutcome


class IngestEndpointSerializer(serializers.ModelSerializer):
    ingest_path = serializers.CharField(read_only=True)
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    org_name = serializers.CharField(source="organization.name", read_only=True)
    captured_count = serializers.SerializerMethodField()

    class Meta:
        model = IngestEndpoint
        fields = [
            "id",
            "name",
            "target_type",
            "organization",
            "org_slug",
            "org_name",
            "state",
            "path_uuid",
            "ingest_path",
            "collection_root_path",
            "idempotency_key_path",
            "field_mappings",
            "entity_mappings",
            "identity_field",
            "max_body_bytes",
            "rate_limit_per_minute",
            "retention_days",
            "captured_count",
            "created_at",
            "updated_at",
        ]
        # state is driven by the activate/pause actions, never set directly.
        read_only_fields = ["id", "path_uuid", "state", "created_at", "updated_at"]

    def get_captured_count(self, obj):
        return obj.captured_payloads.count()

    def validate_field_mappings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("field_mappings must be an object.")
        return value

    def validate_entity_mappings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("entity_mappings must be an object.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class PayloadElementOutcomeSerializer(serializers.ModelSerializer):
    incident_display = serializers.CharField(source="incident.display_id", read_only=True, default=None)
    alert_display = serializers.CharField(source="alert.display_id", read_only=True, default=None)
    asset_name = serializers.CharField(source="asset.name", read_only=True, default=None)

    class Meta:
        model = PayloadElementOutcome
        fields = [
            "id",
            "element_index",
            "idempotency_key",
            "outcome",
            "error",
            "incident_display",
            "alert_display",
            "asset_name",
            "created_at",
        ]


class CapturedPayloadSerializer(serializers.ModelSerializer):
    outcomes = PayloadElementOutcomeSerializer(many=True, read_only=True)

    class Meta:
        model = CapturedPayload
        fields = [
            "id",
            "endpoint",
            "body",
            "status",
            "received_at",
            "processed_at",
            "outcomes",
        ]
