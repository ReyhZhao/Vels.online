from rest_framework import serializers

from .models import Incident, IncidentEvent, Subject


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "slug", "description", "archived", "created_at"]
        read_only_fields = ["id", "slug", "created_at"]


class SubjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["name", "description"]


class SubjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["name", "description", "archived"]


class IncidentSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    assignee_username = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    subject_slug = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()

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
            "closure_reason",
            "subject",
            "subject_slug",
            "subject_name",
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

    def get_subject_slug(self, obj):
        return obj.subject.slug if obj.subject else None

    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None


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
            "subject",
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
            "subject",
            "assignee",
        ]


class IncidentEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = IncidentEvent
        fields = ["id", "kind", "actor", "actor_username", "payload", "created_at"]

    def get_actor_username(self, obj):
        return obj.actor.username if obj.actor else None
