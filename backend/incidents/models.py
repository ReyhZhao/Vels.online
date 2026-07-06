from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from automations.models import Automation, WazuhActiveResponse
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
    wazuh_response = models.ForeignKey(
        WazuhActiveResponse, on_delete=models.SET_NULL, null=True, blank=True, related_name="template_items"
    )

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.template}: {self.title}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.automation_id and self.wazuh_response_id:
            raise ValidationError("A template item cannot have both automation and wazuh_response set.")


class Incident(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_API = "api"
    SOURCE_WAZUH_EVENT = "wazuh_event"
    SOURCE_VULNERABILITY = "vulnerability"
    SOURCE_AGENT_FINDING = "agent_finding"
    SOURCE_INBOUND_EMAIL = "inbound_email"
    SOURCE_WORKFLOW = "workflow"
    SOURCE_EXTERNAL = "external"
    SOURCE_CORRELATION = "correlation"
    SOURCE_SCHEDULED_SEARCH = "scheduled_search"
    SOURCE_THREAT_HUNT = "threat_hunt"
    # Entered directly over email through a configured partner Connection (ADR-0032):
    # a peer CSIRT detection or a supplier bulletin. Never an Alert, never correlated.
    SOURCE_PARTNER = "partner"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_API, "API"),
        (SOURCE_WAZUH_EVENT, "Wazuh Event"),
        (SOURCE_VULNERABILITY, "Vulnerability"),
        (SOURCE_AGENT_FINDING, "Agent Finding"),
        (SOURCE_INBOUND_EMAIL, "Inbound Email"),
        (SOURCE_WORKFLOW, "Workflow"),
        (SOURCE_EXTERNAL, "External"),
        (SOURCE_CORRELATION, "Correlation Rule"),
        (SOURCE_SCHEDULED_SEARCH, "Scheduled Search Rule"),
        (SOURCE_THREAT_HUNT, "Threat Hunt"),
        (SOURCE_PARTNER, "Partner"),
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
    # ADR-0025: the Triage Agent's "threat contained, awaiting human ratification"
    # hand-off — distinct from human-driven resolved.
    STATE_PENDING_CLOSURE = "pending_closure"
    STATE_RESOLVED = "resolved"
    STATE_CLOSED = "closed"
    STATE_CHOICES = [
        (STATE_NEW, "New"),
        (STATE_TRIAGED, "Triaged"),
        (STATE_IN_PROGRESS, "In Progress"),
        (STATE_ON_HOLD, "On Hold"),
        (STATE_NEEDS_TUNING, "Needs Tuning"),
        (STATE_PENDING_CLOSURE, "Pending Closure"),
        (STATE_RESOLVED, "Resolved"),
        (STATE_CLOSED, "Closed"),
    ]

    CLOSURE_RESOLVED = "resolved"
    CLOSURE_FALSE_POSITIVE = "false_positive"
    # True positive, but the incident caused no impact — distinct from a
    # false positive (which was not a real detection at all).
    CLOSURE_NO_IMPACT = "no_impact"
    CLOSURE_DUPLICATE = "duplicate"
    CLOSURE_INFORMATIONAL = "informational"
    CLOSURE_ACCEPTED_RISK = "accepted_risk"
    CLOSURE_REASON_CHOICES = [
        (CLOSURE_RESOLVED, "Resolved"),
        (CLOSURE_FALSE_POSITIVE, "False Positive"),
        (CLOSURE_NO_IMPACT, "No Impact"),
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
    # Free-form labels. Low-risk, reversible — the incident assistant may add these
    # autonomously (ADR-0012).
    tags = models.JSONField(default=list, blank=True)
    # Durable once-per-incident marker for the agentic Triage Work phase (ADR-0024/0025).
    # Set when the Work phase runs so Celery retries of Classify and later-linking alerts
    # never silently re-trigger autonomous actions; the manual triage button clears it to
    # deliberately re-run.
    triage_worked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "created_at"], name="incident_state_ts"),
            models.Index(fields=["severity", "created_at"], name="incident_severity_ts"),
            models.Index(fields=["organization", "created_at"], name="incident_org_ts"),
            models.Index(fields=["organization", "state", "created_at"], name="incident_org_state_ts"),
        ]

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
    TYPE_WAZUH_RESPONSE = "wazuh_response"
    TYPE_CHOICES = [
        (TYPE_MANUAL, "Manual"),
        (TYPE_AUTOMATED, "Automated"),
        (TYPE_WAZUH_RESPONSE, "Wazuh Response"),
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
    wazuh_response = models.ForeignKey(
        WazuhActiveResponse, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
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
        indexes = [
            models.Index(fields=["state", "created_at"], name="task_state_ts"),
        ]

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

    ROLE_WORKSTATION = "workstation"
    ROLE_SERVER = "server"
    ROLE_DNS_SERVER = "dns-server"
    ROLE_DOMAIN_CONTROLLER = "domain-controller"
    ROLE_JUMPHOST = "jumphost"
    ROLE_FIREWALL = "firewall"
    ROLE_ROUTER = "router"
    ROLE_SWITCH = "switch"
    ROLE_DATABASE_SERVER = "database-server"
    ROLE_WEB_SERVER = "web-server"
    ROLE_OTHER = "other"
    ROLE_CHOICES = [
        (ROLE_WORKSTATION, "Workstation"),
        (ROLE_SERVER, "Server"),
        (ROLE_DNS_SERVER, "DNS Server"),
        (ROLE_DOMAIN_CONTROLLER, "Domain Controller"),
        (ROLE_JUMPHOST, "Jumphost"),
        (ROLE_FIREWALL, "Firewall"),
        (ROLE_ROUTER, "Router"),
        (ROLE_SWITCH, "Switch"),
        (ROLE_DATABASE_SERVER, "Database Server"),
        (ROLE_WEB_SERVER, "Web Server"),
        (ROLE_OTHER, "Other"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    name = models.CharField(max_length=255)
    agent_name = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, null=True, blank=True)
    route = models.ForeignKey(
        "ingress.Route", on_delete=models.SET_NULL, null=True, blank=True, related_name="assets"
    )
    is_active = models.BooleanField(default=True)
    is_permanent = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["organization", "is_active"], name="asset_org_active"),
        ]
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


class NatExposure(models.Model):
    PROTOCOL_TCP = "tcp"
    PROTOCOL_UDP = "udp"
    PROTOCOL_CHOICES = [
        (PROTOCOL_TCP, "TCP"),
        (PROTOCOL_UDP, "UDP"),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="nat_exposures")
    protocol = models.CharField(max_length=3, choices=PROTOCOL_CHOICES)
    port = models.PositiveIntegerField()
    public_ip = models.GenericIPAddressField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["protocol", "port"]

    def __str__(self):
        return f"{self.protocol.upper()}/{self.port} on {self.asset}"


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
    KIND_EMAIL = "email"
    KIND_CHOICES = [
        (KIND_IP, "IP Address"),
        (KIND_DOMAIN, "Domain"),
        (KIND_URL, "URL"),
        (KIND_EMAIL, "Email Address"),
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


class WazuhResponseExecution(models.Model):
    wazuh_response = models.ForeignKey(
        WazuhActiveResponse, on_delete=models.PROTECT, related_name="executions"
    )
    executed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="wazuh_executions"
    )
    agent_ids = models.JSONField(default=list)
    resolved_args = models.TextField(blank=True, default="")
    timeout_used = models.PositiveIntegerField(default=0)
    incident = models.ForeignKey(
        Incident, on_delete=models.SET_NULL, null=True, blank=True, related_name="wazuh_executions"
    )
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="wazuh_executions"
    )
    wazuh_status_code = models.IntegerField(null=True, blank=True)
    wazuh_response_body = models.JSONField(default=dict)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at"]

    def __str__(self):
        return f"WazuhExecution {self.pk} ({self.wazuh_response})"


# ── Incident Reporting (PRD #618, ADR-0029) ───────────────────────────────────


class ReportTemplate(models.Model):
    """SOC-authored, global report template (ADR-0029).

    Composed from a fixed catalog of section kinds (never raw markup) plus
    free-text intro/outro/recommendations blocks. ``audience`` fixes the
    visibility floor once, at authoring time: a ``customer`` template renders
    only what an org member could see; an ``internal`` template renders full
    fidelity. Global in v1 (``organization = null``, like a System Rule) —
    tenants cannot author templates.
    """

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_INTERNAL = "internal"
    AUDIENCE_CHOICES = [
        (AUDIENCE_CUSTOMER, "Customer"),
        (AUDIENCE_INTERNAL, "Internal"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True,
        related_name="report_templates",
    )
    name = models.CharField(max_length=255)
    audience = models.CharField(
        max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_CUSTOMER
    )
    # Ordered list of section-kind strings drawn from the server-side catalog
    # (incidents.services.report_sections.SECTION_CATALOG). Ordering is honored
    # at render time.
    sections = models.JSONField(default=list, blank=True)
    intro_text = models.TextField(blank=True, default="")
    outro_text = models.TextField(blank=True, default="")
    recommendations_text = models.TextField(blank=True, default="")
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_report_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.audience})"


class Report(models.Model):
    """An immutable, point-in-time PDF snapshot of one Incident (ADR-0029).

    Denormalized at generation so editing or deleting the source template never
    alters the historical record of what was shared. Stores the rendered PDF via
    the same object-storage backend as Attachments, but is its own entity (not an
    Attachment row).
    """

    AUDIENCE_CUSTOMER = ReportTemplate.AUDIENCE_CUSTOMER
    AUDIENCE_INTERNAL = ReportTemplate.AUDIENCE_INTERNAL

    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name="reports"
    )
    template = models.ForeignKey(
        ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reports",
    )
    # Denormalized snapshot — preserved even if the template is later edited/deleted.
    reference_id = models.CharField(max_length=32, unique=True, blank=True)
    template_name = models.CharField(max_length=255)
    audience = models.CharField(
        max_length=20, choices=ReportTemplate.AUDIENCE_CHOICES
    )
    tlp = models.CharField(max_length=10)
    incident_state = models.CharField(max_length=20)
    # LLM-generated executive summary prose, frozen at generation (PRD #621). Never
    # re-run when an existing Report is viewed/downloaded later.
    executive_summary = models.TextField(blank=True, default="")
    # The rendered section contexts, frozen for audit/immutability.
    content = models.JSONField(default=dict, blank=True)
    s3_key = models.CharField(max_length=500, unique=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="generated_reports",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["incident", "generated_at"]),
        ]

    def __str__(self):
        return f"{self.reference_id} ({self.incident.display_id})"


class TriageLesson(models.Model):
    """A distilled, reusable disposition heuristic the Triage pipeline learns and applies
    (ADR-0030). Keyed on Subject (+ optional source_kind); it *informs* the model's
    judgement and never itself authorizes an action. Two tiers mirror System/Org Rule:
    organization set => Org Lesson (one tenant); organization null => Global Lesson
    (SOC-curated, scrubbed, fleet-wide — the only cross-tenant channel, ADR-0031).
    """

    STATUS_PROPOSED = "proposed"
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_PROPOSED, "Proposed"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    PROV_DISTILLED = "distilled_from_human_close"
    PROV_AGENT = "agent_proposed"
    PROV_STAFF = "staff_authored"
    PROVENANCE_CHOICES = [
        (PROV_DISTILLED, "Distilled from human close"),
        (PROV_AGENT, "Agent proposed"),
        (PROV_STAFF, "Staff authored"),
    ]

    # organization null => Global Lesson (fleet-wide); set => Org Lesson (one tenant).
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True,
        related_name="triage_lessons",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="triage_lessons"
    )
    # "" => applies to any source_kind for the subject; else narrows to that origin.
    source_kind = models.CharField(max_length=20, blank=True, default="")
    # Free-text applicability the model interprets ("applies when source.ip is internal").
    selector = models.TextField(blank=True, default="")
    guidance = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PROPOSED)
    provenance = models.CharField(max_length=32, choices=PROVENANCE_CHOICES)
    # The resolved Incidents that justify this Lesson (audit + grounding). Staff-only on
    # a Global Lesson — never surfaced to a tenant (ADR-0031).
    evidence = models.ManyToManyField(
        Incident, blank=True, related_name="justified_triage_lessons"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_triage_lessons",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_triage_lessons",
    )
    applied_count = models.PositiveIntegerField(default=0)
    last_applied_at = models.DateTimeField(null=True, blank=True)
    contradiction_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["subject", "status"], name="lesson_subject_status"),
            models.Index(fields=["organization", "status"], name="lesson_org_status"),
        ]

    @property
    def is_global(self) -> bool:
        return self.organization_id is None

    def __str__(self):
        tier = "Global" if self.is_global else f"Org:{self.organization_id}"
        return f"TriageLesson[{tier}/{self.subject_id}] {self.status}"


class ClassificationCorrection(models.Model):
    """A human overturning the Triage Classify phase's output on an Incident (ADR-0030) —
    changing its Subject, overriding severity, or reversing the FP/disposition call. The
    strongest self-learning signal: it powers the Classify-accuracy metric, enriches
    Precedents, feeds the distillation sweep, and contradicts the Lesson/Precedent that
    drove the wrong call.
    """

    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name="classification_corrections"
    )
    # The agent's original Classify call and the human's final call. Nullable members so a
    # correction can capture a subject-only, severity-only, or disposition-only change.
    agent_subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    human_subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    agent_severity = models.CharField(max_length=10, blank=True, default="")
    human_severity = models.CharField(max_length=10, blank=True, default="")
    # e.g. "false_positive" -> "true_positive": the human reversed the disposition.
    agent_disposition = models.CharField(max_length=32, blank=True, default="")
    human_disposition = models.CharField(max_length=32, blank=True, default="")
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="classification_corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident", "created_at"], name="correction_incident_ts"),
        ]

    def __str__(self):
        return f"Correction on {self.incident_id} by {self.actor_id}"
