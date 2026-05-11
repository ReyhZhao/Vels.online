from rest_framework import serializers

from .models import ExceptionRule


class ExceptionRuleSerializer(serializers.ModelSerializer):
    org_slug         = serializers.SlugRelatedField(source="organisation", slug_field="slug", read_only=True)
    incident_display_id = serializers.CharField(source="incident.display_id", read_only=True, default=None)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model  = ExceptionRule
        fields = [
            "id",
            "wazuh_rule_id",
            "trigger_rule_id",
            "description",
            "match_value",
            "field_name",
            "field_value",
            "field_type",
            "scope",
            "agent_name",
            "status",
            "org_slug",
            "incident_display_id",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
