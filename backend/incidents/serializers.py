from rest_framework import serializers

from .models import Incident, IncidentEvent


class IncidentSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    assignee_username = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source="organization.slug", read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "display_id",
            "title",
            "description",
            "severity",
            "tlp",
            "pap",
            "state",
            "source_kind",
            "source_ref",
            "org_slug",
            "assignee",
            "assignee_username",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "display_id", "org_slug", "created_by", "created_at", "updated_at"]

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_assignee_username(self, obj):
        return obj.assignee.username if obj.assignee else None


class IncidentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = [
            "title",
            "description",
            "severity",
            "tlp",
            "pap",
            "source_kind",
            "source_ref",
            "assignee",
        ]


class IncidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = [
            "title",
            "description",
            "severity",
            "tlp",
            "pap",
            "assignee",
        ]


class IncidentEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = IncidentEvent
        fields = ["id", "kind", "actor", "actor_username", "payload", "created_at"]

    def get_actor_username(self, obj):
        return obj.actor.username if obj.actor else None
