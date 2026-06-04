from django.conf import settings
from django.db import models


SOURCE_CHOICES = [
    ("wazuh_event", "Wazuh Event"),
    ("vulnerability", "Vulnerability"),
    ("agent_finding", "Agent Finding"),
    ("api", "API"),
    ("inbound_email", "Inbound Email"),
    ("workflow", "Workflow"),
    ("external", "External"),
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
SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

STATE_NEW = "new"
STATE_ACKNOWLEDGED = "acknowledged"
STATE_IMPORTED = "imported"
STATE_IGNORED = "ignored"
STATE_CHOICES = [
    (STATE_NEW, "New"),
    (STATE_ACKNOWLEDGED, "Acknowledged"),
    (STATE_IMPORTED, "Imported"),
    (STATE_IGNORED, "Ignored"),
]


class Alert(models.Model):
    display_id = models.CharField(max_length=20, unique=True, blank=True)
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="alerts"
    )
    source_kind = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    source_ref = models.JSONField(default=dict, blank=True)
    title = models.CharField(max_length=500, blank=True, null=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    pap = models.CharField(max_length=10, choices=PAP_CHOICES, null=True, blank=True)
    tlp = models.CharField(max_length=10, choices=TLP_CHOICES, null=True, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_NEW)
    incident = models.ForeignKey(
        "incidents.Incident",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acknowledged_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_id}: {self.title}"


class AlertEntity(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="entities")
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="alert_entities"
    )
    entity_type = models.CharField(max_length=50)
    value = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["organization", "entity_type", "value", "created_at"],
                name="alertentity_org_type_value_ts",
            ),
        ]

    def __str__(self):
        return f"{self.entity_type}={self.value} ({self.alert_id})"
