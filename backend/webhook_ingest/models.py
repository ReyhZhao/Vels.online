import uuid

from django.conf import settings
from django.db import models

from security.models import Organization


class IngestEndpoint(models.Model):
    """A staff-configured HTTP intake through which a remote system pushes records into the
    platform by POSTing its own-shaped JSON — the webhook sibling of the email Connection
    (CONTEXT.md → Webhook ingest; ADR-0040/0041). Targets exactly one resource type in one
    Organization, and holds the Field Mapping from sender JSON onto that type. Sender auth is
    the secret UUID in its URL path — no token, no ServiceAccount (ADR-0041)."""

    TARGET_INCIDENT = "incident"
    TARGET_ALERT = "alert"
    TARGET_ASSET = "asset"
    TARGET_CHOICES = [
        (TARGET_INCIDENT, "Incident"),
        (TARGET_ALERT, "Alert"),
        (TARGET_ASSET, "Asset"),
    ]

    STATE_CAPTURING = "capturing"
    STATE_ACTIVE = "active"
    STATE_PAUSED = "paused"
    STATE_CHOICES = [
        (STATE_CAPTURING, "Capturing"),
        (STATE_ACTIVE, "Active"),
        (STATE_PAUSED, "Paused"),
    ]

    name = models.CharField(max_length=255)
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="ingest_endpoints"
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_CAPTURING)
    # The secret capability in the URL path — the sole credential (ADR-0041). Rotatable.
    path_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Mapping config (CONTEXT.md → Field Mapping, Collection Root).
    # collection_root_path: JSON path to an array to fan out over ("" = whole body is one record).
    collection_root_path = models.CharField(max_length=500, blank=True, default="")
    # idempotency_key_path: per-element JSON path to the sender's own unique id; "" = content hash.
    idempotency_key_path = models.CharField(max_length=500, blank=True, default="")
    # field_mappings: {canonical_field: {"kind": "path"|"constant", "path"?, "value"?,
    #                  "value_map"?, "default"?}}. "template" kind is reserved for later.
    field_mappings = models.JSONField(default=dict, blank=True)
    # entity_mappings (Alert only): {ecs_field: {"kind": "path"|"constant", ...}}.
    entity_mappings = models.JSONField(default=dict, blank=True)
    # Asset upsert identity (ADR-0040): the mapped field matched within the org. Default "name".
    identity_field = models.CharField(max_length=64, blank=True, default="name")

    # Guardrails (ADR-0041).
    max_body_bytes = models.PositiveIntegerField(default=1_000_000)
    rate_limit_per_minute = models.PositiveIntegerField(default=120)
    retention_days = models.PositiveIntegerField(default=30)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.target_type})"

    @property
    def ingest_path(self):
        return f"/ingest/{self.path_uuid}/"

    def rotate_path(self):
        """Issue a fresh secret path (revokes the old URL)."""
        self.path_uuid = uuid.uuid4()
        self.save(update_fields=["path_uuid", "updated_at"])
        return self.path_uuid


class CapturedPayload(models.Model):
    """One raw JSON body an IngestEndpoint received, stored verbatim with an aggregate status.
    Both the sample corpus the mapping GUI is built against and the endpoint's own dead-letter
    (CONTEXT.md → Captured Payload). Auto-purged after the endpoint's retention window."""

    STATUS_PENDING = "pending"
    STATUS_CREATED = "created"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CREATED, "Created"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PARTIAL, "Partial"),
    ]

    endpoint = models.ForeignKey(
        IngestEndpoint, on_delete=models.CASCADE, related_name="captured_payloads"
    )
    body = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["endpoint", "status", "received_at"], name="cap_ep_status_ts"),
            models.Index(fields=["received_at"], name="cap_received_ts"),
        ]

    def __str__(self):
        return f"CapturedPayload({self.endpoint_id}, {self.status})"


class PayloadElementOutcome(models.Model):
    """The result of materialising one fanned-out element of a CapturedPayload. One row per
    element; the unit Replay re-runs (skipping already-`created` rows). Denormalises the
    endpoint so per-endpoint idempotency dedup is a single indexed lookup."""

    OUTCOME_CREATED = "created"
    OUTCOME_FAILED = "failed"
    OUTCOME_SKIPPED = "skipped"
    OUTCOME_CHOICES = [
        (OUTCOME_CREATED, "Created"),
        (OUTCOME_FAILED, "Failed"),
        (OUTCOME_SKIPPED, "Skipped"),
    ]

    captured_payload = models.ForeignKey(
        CapturedPayload, on_delete=models.CASCADE, related_name="outcomes"
    )
    endpoint = models.ForeignKey(
        IngestEndpoint, on_delete=models.CASCADE, related_name="outcomes"
    )
    element_index = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    error = models.TextField(blank=True, default="")

    # Which record this element produced (only one is set, per the endpoint's target type).
    # SET_NULL so a record deleted downstream doesn't strand the audit row.
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    alert = models.ForeignKey(
        "alerts.Alert", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    asset = models.ForeignKey(
        "incidents.Asset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_payload", "element_index"]
        unique_together = [("captured_payload", "element_index")]
        indexes = [
            models.Index(
                fields=["endpoint", "idempotency_key", "outcome"], name="outcome_ep_idem_idx"
            ),
        ]

    def __str__(self):
        return f"Outcome({self.captured_payload_id}#{self.element_index}={self.outcome})"
