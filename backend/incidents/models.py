from django.contrib.auth.models import User
from django.db import models

from security.models import Organization


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
    STATE_CHOICES = [
        (STATE_NEW, "New"),
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
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_incidents"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_incidents"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_id}: {self.title}"


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
