from django.utils import timezone
from rest_framework import serializers

from .models import Attachment, Comment, Incident, IncidentDelegation, IncidentEvent, Subject, Task, TaskTemplate, TaskTemplateItem


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


class IncidentDelegationSerializer(serializers.ModelSerializer):
    delegate_username = serializers.SerializerMethodField()
    delegated_by_username = serializers.SerializerMethodField()

    class Meta:
        model = IncidentDelegation
        fields = [
            "id", "user", "delegate_username", "delegated_by", "delegated_by_username",
            "delegated_at", "note",
        ]

    def get_delegate_username(self, obj):
        return obj.user.username if obj.user else None

    def get_delegated_by_username(self, obj):
        return obj.delegated_by.username if obj.delegated_by else None


class IncidentSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    assignee_username = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    subject_slug = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    active_delegations = serializers.SerializerMethodField()

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
            "active_delegations",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "display_id", "org_slug", "created_by", "created_at", "updated_at"]

    def get_active_delegations(self, obj):
        qs = obj.delegations.filter(returned_at__isnull=True).select_related("user", "delegated_by")
        return IncidentDelegationSerializer(qs, many=True).data

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


class TaskTemplateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplateItem
        fields = ["id", "title", "description", "display_order"]


class TaskTemplateItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplateItem
        fields = ["title", "description", "display_order"]


class TaskTemplateSerializer(serializers.ModelSerializer):
    items = TaskTemplateItemSerializer(many=True, read_only=True)
    subject_slug = serializers.CharField(source="subject.slug", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    created_by_username = serializers.SerializerMethodField()

    class Meta:
        model = TaskTemplate
        fields = [
            "id", "name", "subject", "subject_slug", "subject_name",
            "description", "is_auto_apply", "archived",
            "created_by", "created_by_username", "created_at", "updated_at",
            "items",
        ]
        read_only_fields = ["id", "subject_slug", "subject_name", "created_by", "created_at", "updated_at"]

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None


class TaskTemplateWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplate
        fields = ["name", "subject", "description", "is_auto_apply"]


class TaskTemplatePatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplate
        fields = ["name", "description", "is_auto_apply", "archived"]


class TaskSerializer(serializers.ModelSerializer):
    template_name = serializers.SerializerMethodField()
    assignee_username = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id", "incident", "template_item", "template_name",
            "title", "description", "state",
            "assignee", "assignee_username", "display_order",
            "created_at", "closed_at",
        ]
        read_only_fields = ["id", "incident", "created_at"]

    def get_template_name(self, obj):
        if obj.template_item_id and obj.template_item and obj.template_item.template:
            return obj.template_item.template.name
        return None

    def get_assignee_username(self, obj):
        return obj.assignee.username if obj.assignee else None


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["title", "description", "display_order", "assignee"]


class TaskPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["title", "description", "state", "assignee", "display_order"]


class IncidentEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = IncidentEvent
        fields = ["id", "kind", "actor", "actor_username", "payload", "created_at"]

    def get_actor_username(self, obj):
        return obj.actor.username if obj.actor else None


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id", "incident", "task", "author", "author_username",
            "body", "is_internal", "created_at", "updated_at", "deleted_at", "can_edit",
        ]
        read_only_fields = ["id", "incident", "task", "author", "created_at", "updated_at"]

    def get_author_username(self, obj):
        return obj.author.username if obj.author else None

    def get_can_edit(self, obj):
        if obj.deleted_at:
            return False
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if obj.author_id != request.user.id:
            return False
        return (timezone.now() - obj.created_at).total_seconds() < 900


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["body", "is_internal"]


class CommentPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["body"]


class AttachmentSerializer(serializers.ModelSerializer):
    uploader_username = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id", "filename", "size_bytes", "content_type", "sha256",
            "is_internal", "uploader", "uploader_username", "created_at", "confirmed_at",
        ]
        read_only_fields = fields

    def get_uploader_username(self, obj):
        return obj.uploader.username if obj.uploader else None
