from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import Asset, Attachment, Comment, IOC, Incident, IncidentAsset, IncidentDelegation, IncidentEvent, NatExposure, Subject, Task, TaskTemplate, TaskTemplateItem
from .tasks import get_triage_lock_started_at


class IOCSerializer(serializers.ModelSerializer):
    class Meta:
        model = IOC
        fields = ["id", "kind", "value", "enrichment_data", "created_at"]
        read_only_fields = ["id", "enrichment_data", "created_at"]


class IOCWriteSerializer(serializers.ModelSerializer):
    """Write serializer for analyst-managed IOCs (#604).

    `kind`/`value` are client-settable; `enrichment_data`, `created_at`, and
    `incident` stay server-managed. The (incident, kind, value) uniqueness is
    enforced in the view so a collision returns a clean 400, not a 500.
    """
    kind = serializers.ChoiceField(choices=IOC.KIND_CHOICES)
    value = serializers.CharField(trim_whitespace=True)

    class Meta:
        model = IOC
        fields = ["kind", "value"]

    def validate_value(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class SubjectSerializer(serializers.ModelSerializer):
    # Number of Classification Corrections touching this subject (ADR-0030) — a
    # Classify-accuracy troubleshooting signal. Only populated for staff, on the list
    # endpoint; null otherwise so tenants never see cross-org correction volume.
    correction_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ["id", "name", "slug", "description", "archived", "created_at", "correction_count"]
        read_only_fields = ["id", "slug", "created_at", "correction_count"]

    def get_correction_count(self, obj):
        return getattr(obj, "_correction_count", None)


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


def _compute_sla(incident, kind):
    targets = getattr(settings, "INCIDENT_SLA_TARGETS", {})
    sev_targets = targets.get(incident.severity)
    if not sev_targets:
        return None
    target = sev_targets.get(f"{kind}_seconds")
    if target is None:
        return None

    if kind == "response":
        applies = incident.state == "new"
    else:
        applies = incident.state not in ("resolved", "closed")

    elapsed = int((timezone.now() - incident.created_at).total_seconds())
    remaining = target - elapsed
    return {
        "target_seconds": target,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "breached": elapsed > target,
        "applies": applies,
    }


class NatExposureSerializer(serializers.ModelSerializer):
    class Meta:
        model = NatExposure
        fields = ["id", "protocol", "port", "public_ip", "description", "created_at"]
        read_only_fields = ["id", "created_at"]


class AssetSerializer(serializers.ModelSerializer):
    route_fqdn = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    internet_facing = serializers.SerializerMethodField()
    exposures = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id", "kind", "name", "agent_name", "ip_address", "role",
            "route", "route_fqdn", "org_slug", "is_active", "is_permanent",
            "last_seen_at", "created_at", "internet_facing", "exposures",
        ]
        read_only_fields = ["id", "created_at"]

    def get_route_fqdn(self, obj):
        return obj.route.fqdn if obj.route else None

    def get_internet_facing(self, obj):
        if obj.kind != Asset.KIND_HOST:
            return False
        if hasattr(obj, "internet_facing"):
            return bool(obj.internet_facing)
        cache = getattr(obj, "_prefetched_objects_cache", {})
        if "route_exposures" in cache:
            return bool(obj.route_exposures.all()) or bool(obj.nat_exposures.all())
        from incidents.services.exposures import host_exposures
        return bool(host_exposures(obj))

    def get_exposures(self, obj):
        if obj.kind != Asset.KIND_HOST:
            return []
        result = []
        # Use prefetched relations when available (list view path) to avoid N+1.
        cache = getattr(obj, "_prefetched_objects_cache", {})
        if "route_exposures" in cache:
            for route in obj.route_exposures.all():
                result.append({"kind": "ingress_route", "protection": "protected",
                                "specifics": {"fqdn": route.fqdn, "backend_port": route.backend_port}})
            for nat in obj.nat_exposures.all():
                result.append({"kind": "direct_nat", "protection": "raw",
                                "specifics": {"protocol": nat.protocol, "port": nat.port,
                                              "public_ip": str(nat.public_ip) if nat.public_ip else None,
                                              "description": nat.description or None, "id": nat.pk}})
            return result
        from incidents.services.exposures import host_exposures
        return [
            {"kind": e.kind, "protection": e.protection, "specifics": e.specifics}
            for e in host_exposures(obj)
        ]


class IncidentAssetSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)
    added_by_username = serializers.SerializerMethodField()

    class Meta:
        model = IncidentAsset
        fields = ["id", "asset", "added_by", "added_by_username", "added_at"]

    def get_added_by_username(self, obj):
        return obj.added_by.username if obj.added_by else None


class IncidentStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = ["id", "display_id", "title", "state", "severity", "created_at"]


class IncidentSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    assignee_username = serializers.SerializerMethodField()
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    org_name = serializers.CharField(source="organization.name", read_only=True)
    subject_slug = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    active_delegations = serializers.SerializerMethodField()
    response_sla = serializers.SerializerMethodField()
    resolve_sla = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    iocs = serializers.SerializerMethodField()
    duplicate_of_display_id = serializers.SerializerMethodField()
    duplicates = serializers.SerializerMethodField()
    triage_running = serializers.SerializerMethodField()
    triage_started_at = serializers.SerializerMethodField()
    linked_alert_count = serializers.SerializerMethodField()
    attachment_count = serializers.SerializerMethodField()
    task_count = serializers.SerializerMethodField()
    contact_count = serializers.SerializerMethodField()

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
            "duplicate_of",
            "duplicate_of_display_id",
            "duplicates",
            "subject",
            "subject_slug",
            "subject_name",
            "source_kind",
            "source_ref",
            "org_slug",
            "org_name",
            "assignee",
            "assignee_username",
            "active_delegations",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
            "response_sla",
            "resolve_sla",
            "assets",
            "iocs",
            "triage_running",
            "triage_started_at",
            "linked_alert_count",
            "attachment_count",
            "task_count",
            "contact_count",
        ]
        read_only_fields = ["id", "display_id", "org_slug", "org_name", "created_by", "created_at", "updated_at"]

    def get_assets(self, obj):
        qs = getattr(obj, "_prefetched_incident_assets", None)
        if qs is None:
            qs = obj.incident_assets.select_related("asset__route", "added_by")
        return IncidentAssetSerializer(qs, many=True).data

    def get_iocs(self, obj):
        return IOCSerializer(obj.iocs.all(), many=True).data

    def get_active_delegations(self, obj):
        cached = getattr(obj, "_active_delegations", None)
        if cached is not None:
            return IncidentDelegationSerializer(cached, many=True).data
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

    def get_response_sla(self, obj):
        return _compute_sla(obj, "response")

    def get_resolve_sla(self, obj):
        return _compute_sla(obj, "resolve")

    def get_duplicate_of_display_id(self, obj):
        return obj.duplicate_of.display_id if obj.duplicate_of_id else None

    def get_duplicates(self, obj):
        return IncidentStubSerializer(obj.duplicates.all(), many=True).data


    def get_triage_running(self, obj):
        return get_triage_lock_started_at(obj.id) is not None

    def get_triage_started_at(self, obj):
        return get_triage_lock_started_at(obj.id)

    def get_linked_alert_count(self, obj):
        v = getattr(obj, "_alert_count", None)
        return v if v is not None else obj.alerts.count()

    def get_attachment_count(self, obj):
        v = getattr(obj, "_attachment_count", None)
        return v if v is not None else obj.attachments.count()

    def get_task_count(self, obj):
        v = getattr(obj, "_task_count", None)
        return v if v is not None else obj.tasks.count()

    def get_contact_count(self, obj):
        v = getattr(obj, "_contact_count", None)
        return v if v is not None else obj.incident_contacts.count()


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


CONTACT_TASK_ROLES = {"", "notified", "questioned", "update"}


def _validate_template_item_flavor(attrs):
    """At most one action flavor per item; a contact item needs a body and a valid role."""
    flavors = [bool(attrs.get("automation")), bool(attrs.get("wazuh_response")), bool(attrs.get("is_contact_task"))]
    if sum(flavors) > 1:
        raise serializers.ValidationError(
            "A template item can have at most one of automation, wazuh_response, or contact."
        )
    if attrs.get("is_contact_task") and not (attrs.get("contact_body") or "").strip():
        raise serializers.ValidationError({"contact_body": "A contact task requires a message body."})
    if (attrs.get("contact_role") or "") not in CONTACT_TASK_ROLES:
        raise serializers.ValidationError({"contact_role": "Invalid contact role."})
    return attrs


class TaskTemplateItemSerializer(serializers.ModelSerializer):
    automation_name = serializers.CharField(source="automation.name", read_only=True, default=None)
    wazuh_response_name = serializers.CharField(source="wazuh_response.name", read_only=True, default=None)

    class Meta:
        model = TaskTemplateItem
        fields = ["id", "title", "description", "display_order", "automation", "automation_name",
                  "wazuh_response", "wazuh_response_name", "is_contact_task", "contact_role", "contact_body"]

    def validate(self, attrs):
        return _validate_template_item_flavor(attrs)


class TaskTemplateItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTemplateItem
        fields = ["title", "description", "display_order", "automation", "wazuh_response",
                  "is_contact_task", "contact_role", "contact_body"]

    def validate(self, attrs):
        return _validate_template_item_flavor(attrs)


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
    incident_display_id = serializers.SerializerMethodField()
    incident_title = serializers.SerializerMethodField()
    automation_name = serializers.CharField(source="automation.name", read_only=True, default=None)
    wazuh_response_name = serializers.CharField(source="wazuh_response.name", read_only=True, default=None)
    wazuh_response_command = serializers.CharField(source="wazuh_response.command", read_only=True, default=None)
    wazuh_response_requires_confirmation = serializers.BooleanField(source="wazuh_response.requires_confirmation", read_only=True, default=False)

    class Meta:
        model = Task
        fields = [
            "id", "incident", "template_item", "template_name",
            "title", "description", "state",
            "task_type", "automation", "automation_name",
            "wazuh_response", "wazuh_response_name", "wazuh_response_command", "wazuh_response_requires_confirmation",
            "contact_role", "contact_body",
            "semaphore_task_id", "automation_error",
            "assignee", "assignee_username", "display_order",
            "created_at", "closed_at",
            "incident_display_id", "incident_title",
        ]
        read_only_fields = ["id", "incident", "created_at", "semaphore_task_id", "automation_error"]

    def get_template_name(self, obj):
        if obj.template_item_id and obj.template_item and obj.template_item.template:
            return obj.template_item.template.name
        return None

    def get_assignee_username(self, obj):
        return obj.assignee.username if obj.assignee else None

    def get_incident_display_id(self, obj):
        return obj.incident.display_id if obj.incident_id else None

    def get_incident_title(self, obj):
        return obj.incident.title if obj.incident_id else None


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["title", "description", "display_order", "assignee", "task_type", "automation",
                  "wazuh_response", "contact_role", "contact_body"]

    def validate(self, attrs):
        if attrs.get("task_type") == "automated" and not attrs.get("automation"):
            raise serializers.ValidationError({"automation": "An automation must be selected when task type is automated."})
        if attrs.get("task_type") == "wazuh_response" and not attrs.get("wazuh_response"):
            raise serializers.ValidationError({"wazuh_response": "A Wazuh response must be selected when task type is wazuh_response."})
        if attrs.get("task_type") == "contact" and not (attrs.get("contact_body") or "").strip():
            raise serializers.ValidationError({"contact_body": "A message body is required for a contact task."})
        return attrs


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
            "kind", "origin", "body", "metadata", "is_internal", "created_at", "updated_at", "deleted_at", "can_edit",
        ]
        read_only_fields = ["id", "incident", "task", "author", "kind", "origin", "metadata", "created_at", "updated_at"]

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


# ── Incident Reporting (PRD #618, ADR-0029) ───────────────────────────────────

from .models import Report, ReportTemplate  # noqa: E402


class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()

    class Meta:
        model = ReportTemplate
        fields = [
            "id", "name", "audience", "sections",
            "intro_text", "outro_text", "recommendations_text",
            "archived", "created_by", "created_by_username",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_by_username", "created_at", "updated_at"]

    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else None

    def validate_sections(self, value):
        from .services.report_sections import catalog_kinds

        if not isinstance(value, list):
            raise serializers.ValidationError("sections must be a list of section kinds.")
        valid = set(catalog_kinds())
        for kind in value:
            if kind not in valid:
                raise serializers.ValidationError(
                    f"Unknown section kind '{kind}'. Valid kinds: {', '.join(sorted(valid))}."
                )
        return value


class ReportSerializer(serializers.ModelSerializer):
    generated_by_username = serializers.SerializerMethodField()
    incident_display_id = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id", "reference_id", "template", "template_name", "audience",
            "tlp", "incident_state", "incident_display_id", "organization_name",
            "generated_by", "generated_by_username", "generated_at", "size_bytes",
        ]
        read_only_fields = fields

    def get_generated_by_username(self, obj):
        return obj.generated_by.username if obj.generated_by else None

    def get_incident_display_id(self, obj):
        return obj.incident.display_id

    def get_organization_name(self, obj):
        return obj.incident.organization.name if obj.incident.organization_id else None
