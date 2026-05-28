from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from automations.models import Automation
from security.models import Organization


class Subject(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TaskTemplate(models.Model):
    name = models.CharField(max_length=255)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="task_templates")
    description = models.TextField(blank=True, default="")
    is_auto_apply = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_task_templates"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.subject})"


class TaskTemplateItem(models.Model):
    template = models.ForeignKey(TaskTemplate, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    automation = models.ForeignKey(
        Automation, on_delete=models.SET_NULL, null=True, blank=True, related_name="template_items"
    )

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.template}: {self.title}"


class Incident(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_API = "api"
    SOURCE_WAZUH_EVENT = "wazuh_event"
    SOURCE_VULNERABILITY = "vulnerability"
    SOURCE_AGENT_FINDING = "agent_finding"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_API, "API"),
        (SOURCE_WAZUH_EVENT, "Wazuh Event"),
        (SOURCE_VULNERABILITY, "Vulnerability"),
        (SOURCE_AGENT_FINDING, "Agent Finding"),
    ]

    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_INFO = "info"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_LOW, "Low"),
        (SEVERITY_INFO, "Info"),
    ]

    TLP_WHITE = "white"
    TLP_GREEN = "green"
    TLP_AMBER = "amber"
    TLP_RED = "red"
    TLP_CHOICES = [
        (TLP_WHITE, "TLP:WHITE"),
        (TLP_GREEN, "TLP:GREEN"),
        (TLP_AMBER, "TLP:AMBER"),
        (TLP_RED, "TLP:RED"),
    ]

    PAP_WHITE = "white"
    PAP_GREEN = "green"
    PAP_AMBER = "amber"
    PAP_RED = "red"
    PAP_CHOICES = [
        (PAP_WHITE, "PAP:WHITE"),
        (PAP_GREEN, "PAP:GREEN"),
        (PAP_AMBER, "PAP:AMBER"),
        (PAP_RED, "PAP:RED"),
    ]

    STATE_NEW = "new"
    STATE_TRIAGED = "triaged"
    STATE_IN_PROGRESS = "in_progress"
    STATE_ON_HOLD = "on_hold"
    STATE_NEEDS_TUNING = "needs_tuning"
    STATE_RESOLVED = "resolved"
    STATE_CLOSED = "closed"
    STATE_CHOICES = [
        (STATE_NEW, "New"),
        (STATE_TRIAGED, "Triaged"),
        (STATE_IN_PROGRESS, "In Progress"),
        (STATE_ON_HOLD, "On Hold"),
        (STATE_NEEDS_TUNING, "Needs Tuning"),
        (STATE_RESOLVED, "Resolved"),
        (STATE_CLOSED, "Closed"),
    ]

    CLOSURE_RESOLVED = "resolved"
    CLOSURE_FALSE_POSITIVE = "false_positive"
    CLOSURE_DUPLICATE = "duplicate"
    CLOSURE_INFORMATIONAL = "informational"
    CLOSURE_ACCEPTED_RISK = "accepted_risk"
    CLOSURE_REASON_CHOICES = [
        (CLOSURE_RESOLVED, "Resolved"),
        (CLOSURE_FALSE_POSITIVE, "False Positive"),
        (CLOSURE_DUPLICATE, "Duplicate"),
        (CLOSURE_INFORMATIONAL, "Informational"),
        (CLOSURE_ACCEPTED_RISK, "Accepted Risk"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="incidents")
    source_kind = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    source_ref = models.JSONField(default=dict, blank=True)
    display_id = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM)
    tlp = models.CharField(max_length=10, choices=TLP_CHOICES, default=TLP_AMBER)
    pap = models.CharField(max_length=10, choices=PAP_CHOICES, default=PAP_AMBER)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_NEW)
    closure_reason = models.CharField(
        max_length=20, choices=CLOSURE_REASON_CHOICES, null=True, blank=True
    )
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents"
    )
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_incidents"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_incidents"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assets = models.ManyToManyField(
        "Asset", through="IncidentAsset", related_name="incidents", blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_id}: {self.title}"


class Task(models.Model):
    STATE_NEW = "new"
    STATE_IN_PROGRESS = "in_progress"
    STATE_DONE = "done"
    STATE_CANCELLED = "cancelled"
    STATE_CHOICES = [
        (STATE_NEW, "New"),
        (STATE_IN_PROGRESS, "In Progress"),
        (STATE_DONE, "Done"),
        (STATE_CANCELLED, "Cancelled"),
    ]

    TYPE_MANUAL = "manual"
    TYPE_AUTOMATED = "automated"
    TYPE_CHOICES = [
        (TYPE_MANUAL, "Manual"),
        (TYPE_AUTOMATED, "Automated"),
    ]

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="tasks")
    template_item = models.ForeignKey(
        TaskTemplateItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_NEW)
    task_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MANUAL)
    automation = models.ForeignKey(
        Automation, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    semaphore_task_id = models.IntegerField(null=True, blank=True)
    automation_error = models.TextField(null=True, blank=True)
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks"
    )
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return f"{self.incident}: {self.title}"


class IncidentTemplateApplication(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="template_applications")
    template = models.ForeignKey(TaskTemplate, on_delete=models.CASCADE, related_name="applications")
    applied_at = models.DateTimeField(auto_now_add=True)
    applied_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="template_applications"
    )

    class Meta:
        ordering = ["-applied_at"]

    def __str__(self):
        return f"{self.template} applied to {self.incident}"


class IncidentEvent(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=50)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="incident_events"
    )
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self):
        return f"{self.kind} on {self.incident} at {self.created_at}"


class IncidentDelegation(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="delegations")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="incident_delegations"
    )
    delegated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="delegations_created"
    )
    delegated_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="delegations_returned"
    )
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["delegated_at"]

    def __str__(self):
        return f"{self.incident} delegated to {self.user}"

    @property
    def is_active(self):
        return self.returned_at is None


class Comment(models.Model):
    KIND_USER = "user"
    KIND_AI_TRIAGE = "ai_triage"
    KIND_SYSTEM = "system"
    KIND_AI_TASK_SUMMARY = "ai_task_summary"
    KIND_CHOICES = [
        (KIND_USER, "User"),
        (KIND_AI_TRIAGE, "AI Triage"),
        (KIND_SYSTEM, "System"),
        (KIND_AI_TASK_SUMMARY, "AI Task Summary"),
    ]

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="comments")
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="comments"
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="comments"
    )
    body = models.TextField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_USER)
    metadata = models.JSONField(null=True, blank=True)
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(incident__isnull=False),
                name="comment_incident_not_null",
            )
        ]

    def clean(self):
        if self.task_id and self.incident_id:
            if self.task.incident_id != self.incident_id:
                raise ValidationError("task.incident must match comment.incident")

    def __str__(self):
        return f"Comment {self.id} on {self.incident}"


class Attachment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="attachments")
    uploader = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_attachments"
    )
    s3_key = models.CharField(max_length=500, unique=True)
    filename = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    sha256 = models.CharField(max_length=64, blank=True, default="")
    is_internal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.filename} on {self.incident}"


class Asset(models.Model):
    KIND_HOST = "host"
    KIND_ROUTE = "route"
    KIND_CHOICES = [
        (KIND_HOST, "Host"),
        (KIND_ROUTE, "Route"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    name = models.CharField(max_length=255)
    agent_name = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    route = models.ForeignKey(
        "ingress.Route", on_delete=models.SET_NULL, null=True, blank=True, related_name="assets"
    )
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "agent_name"],
                condition=models.Q(kind="host"),
                name="unique_host_asset_per_org",
            ),
            models.UniqueConstraint(
                fields=["route"],
                condition=models.Q(kind="route"),
                name="unique_route_asset",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.kind})"


class IncidentAsset(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="incident_assets")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="incident_assets")
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="added_incident_assets"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("incident", "asset")]
        ordering = ["added_at"]

    def __str__(self):
        return f"{self.asset} on {self.incident}"


class IOC(models.Model):
    KIND_IP = "ip"
    KIND_DOMAIN = "domain"
    KIND_URL = "url"
    KIND_CHOICES = [
        (KIND_IP, "IP Address"),
        (KIND_DOMAIN, "Domain"),
        (KIND_URL, "URL"),
    ]

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="iocs")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    value = models.TextField()
    enrichment_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "value"]
        unique_together = [("incident", "kind", "value")]

    def __str__(self):
        return f"{self.kind}: {self.value} ({self.incident})"
