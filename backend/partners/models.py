from django.conf import settings
from django.db import models

from security.models import Organization


class Connection(models.Model):
    """A staff-configured, per-external-organisation email channel through which an
    outside party feeds Incidents into the platform over email (CONTEXT.md → Partner
    intake; ADR-0032). Two kinds: a CSIRT/peer Connection feeding one customer org
    (usually bidirectional), and a Vendor Connection feeding the Infrastructure org
    with supplier bulletins (inbound-only)."""

    KIND_CSIRT_PEER = "csirt_peer"
    KIND_VENDOR = "vendor"
    KIND_CHOICES = [
        (KIND_CSIRT_PEER, "CSIRT / Peer"),
        (KIND_VENDOR, "Vendor"),
    ]

    DIRECTION_INBOUND_ONLY = "inbound_only"
    DIRECTION_BIDIRECTIONAL = "bidirectional"
    DIRECTION_CHOICES = [
        (DIRECTION_INBOUND_ONLY, "Inbound only"),
        (DIRECTION_BIDIRECTIONAL, "Bidirectional"),
    ]

    # Subject carried by Vendor Connection incidents (CONTEXT.md → Vendor Advisory).
    VENDOR_ADVISORY_SUBJECT = "Vendor Advisory"

    # Incident fields the per-field extraction engine (slice 2, ADR-0032) can map onto.
    MAPPED_FIELDS = ("severity", "tlp", "pap", "title", "description")

    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_CSIRT_PEER)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="partner_connections"
    )
    direction = models.CharField(
        max_length=20, choices=DIRECTION_CHOICES, default=DIRECTION_BIDIRECTIONAL
    )
    # Regex over the email subject that captures the partner's External Reference
    # (their own case/advisory id). Empty = no reference extraction.
    external_reference_regex = models.CharField(max_length=500, blank=True, default="")
    # Per-field extraction config keyed by MAPPED_FIELDS field name, each
    # {"regex": str?, "value_map": {..}?, "default": str}. Consumed by the
    # field-mapping engine in slice 2.
    field_mappings = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partner_connections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ConnectionSender(models.Model):
    """One sender email address for a Connection. The address is unique across ALL
    Connections so inbound routing (from_address → Connection) is unambiguous (ADR-0032:
    one sender maps to exactly one Connection/org)."""

    connection = models.ForeignKey(
        Connection, on_delete=models.CASCADE, related_name="senders"
    )
    address = models.EmailField(unique=True)

    class Meta:
        ordering = ["address"]

    def __str__(self):
        return self.address


class IntakeInboxMessage(models.Model):
    """A staff-only dead-letter row for an inbound email that reached the SOC mailbox but
    no handler accepted — an unknown sender, a Connection sender that failed DKIM/SPF, or
    otherwise un-routable mail (incl. misfired phishing forwards). Carries bounded
    metadata plus, for Replay, the retained raw `.eml` (in object storage, never the DB);
    its primary action is "Create Connection" pre-filling the sender. Row and raw object
    are auto-purged together after a retention window (CONTEXT.md → Intake Inbox, Replay;
    ADR-0035)."""

    sender = models.CharField(max_length=320, blank=True, default="")
    subject = models.CharField(max_length=500, blank=True, default="")
    drop_reason = models.CharField(max_length=100, blank=True, default="")
    body_excerpt = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    # Object-storage key for the retained raw `.eml` (empty = none retained, e.g. a
    # storage failure at capture or the bytes dropped after a successful replay). Bytes
    # live under an isolated `intake-inbox/{id}/` prefix, never in the DB (ADR-0035).
    raw_s3_key = models.CharField(max_length=1024, blank=True, default="")
    # Replay markers (ADR-0035): set once this row has been re-run through the live
    # partner pipeline into an Incident. Idempotency is per-row — replay skips marked rows.
    replayed_at = models.DateTimeField(null=True, blank=True)
    replayed_incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["received_at"], name="intake_received_idx")]

    def __str__(self):
        return f"{self.sender} — {self.drop_reason}"
