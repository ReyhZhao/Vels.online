from django.conf import settings
from django.db import models


SOURCE_CHOICES = [
    ("wazuh_event", "Wazuh Event"),
    ("vulnerability", "Vulnerability"),
    ("agent_finding", "Agent Finding"),
    ("api", "API"),
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
    title = models.CharField(max_length=500, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM)
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
