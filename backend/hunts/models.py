"""Persisted Hunt aggregate (ADR-0015, ADR-0016).

A **Hunt** is a staff-initiated, LLM-assisted threat-hunting investigation. Unlike
the ephemeral Incident Assistant conversation, a Hunt is a first-class persisted,
resumable, auditable entity: its durable transcript (HuntEvent rows) *is* its
grounding, its matched docs are HuntFindings grouped by org, and any incident it
spawns is linked back via HuntFinding.materialised_incident.
"""
import uuid

from django.conf import settings
from django.db import models

from security.models import Organization


class Hunt(models.Model):
    SEED_QUESTION = "question"
    SEED_URL = "url"
    SEED_CHOICES = [
        (SEED_QUESTION, "Question"),
        (SEED_URL, "Report URL"),
    ]

    STATUS_CREATED = "created"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_ERROR, "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="hunts",
    )
    title = models.CharField(max_length=255, blank=True, default="")

    seed_kind = models.CharField(max_length=16, choices=SEED_CHOICES, default=SEED_QUESTION)
    # The free-text question, or (for a URL seed) the fetched/extracted report text.
    seed_text = models.TextField(blank=True, default="")
    seed_url = models.URLField(max_length=2000, blank=True, default="")

    # Cross-org scope. all_orgs is the default sweep; when False, scope_orgs lists
    # the tenants to hunt. Tenant isolation holds regardless — every lens fans out
    # per org and never joins across tenants.
    scope_all_orgs = models.BooleanField(default=True)
    scope_orgs = models.ManyToManyField(Organization, blank=True, related_name="hunts")
    lookback_days = models.PositiveIntegerField(default=30)

    # The running LLM message transcript (without the system prompt), persisted after
    # each turn so a Hunt is resumable — a follow-up turn continues from here.
    transcript = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_CREATED)
    # Cooperative cancel flag the Celery turn checks at each iteration (ADR-0016).
    # A dropped SSE socket must NOT set this — only an explicit cancel does.
    cancel_requested = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Hunt {self.id} ({self.status})"

    @property
    def is_terminal(self):
        return self.status in (self.STATUS_COMPLETED, self.STATUS_CANCELLED, self.STATUS_ERROR)


class HuntEvent(models.Model):
    """One entry on a Hunt's append-only event log (ADR-0016).

    This is both the SSE streaming source (the tail/replay endpoint reads from here)
    and part of the audit trail. `seq` is a per-hunt monotonically increasing index
    so a reconnecting client can resume from the last seq it saw.
    """
    TYPE_PHASE = "phase"
    TYPE_TOOL = "tool"
    TYPE_ACTION = "action"
    TYPE_RESULT = "result"
    TYPE_ERROR = "error"
    TYPE_DONE = "done"

    hunt = models.ForeignKey(Hunt, on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    turn = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=16)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        unique_together = [("hunt", "seq")]

    def __str__(self):
        return f"{self.hunt_id}#{self.seq} {self.type}"


class HuntFinding(models.Model):
    """A raw Wazuh document a Hunt lens matched, tagged with its owning org.

    Findings are grouped by org and become a propose-and-confirm Incident; on confirm
    they are materialised as Alerts linked to that incident (reusing the Scheduled
    Search Rule bridge). Idempotent per (hunt, source_index, wazuh_doc_id).
    """
    hunt = models.ForeignKey(Hunt, on_delete=models.CASCADE, related_name="findings")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="hunt_findings")
    lens = models.CharField(max_length=64, blank=True, default="")
    source_index = models.CharField(max_length=255, blank=True, default="")
    wazuh_doc_id = models.CharField(max_length=255, blank=True, default="")
    raw_doc = models.JSONField(default=dict, blank=True)
    summary = models.CharField(max_length=500, blank=True, default="")
    materialised_incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hunt_findings",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization_id", "created_at"]
        unique_together = [("hunt", "source_index", "wazuh_doc_id")]

    def __str__(self):
        return f"Finding {self.wazuh_doc_id} ({self.organization_id})"
