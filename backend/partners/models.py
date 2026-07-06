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
