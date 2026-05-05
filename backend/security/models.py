from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Download(models.Model):
    PLATFORM_WINDOWS = "windows"
    PLATFORM_LINUX = "linux"
    PLATFORM_MACOS = "macos"
    PLATFORM_ALL = "all"
    PLATFORM_CHOICES = [
        (PLATFORM_WINDOWS, "Windows"),
        (PLATFORM_LINUX, "Linux"),
        (PLATFORM_MACOS, "macOS"),
        (PLATFORM_ALL, "All"),
    ]

    CATEGORY_AGENT = "agent"
    CATEGORY_TOOL = "tool"
    CATEGORY_CONFIG = "config"
    CATEGORY_CHOICES = [
        (CATEGORY_AGENT, "Agent"),
        (CATEGORY_TOOL, "Tool"),
        (CATEGORY_CONFIG, "Config"),
    ]

    label = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=500, blank=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default=PLATFORM_ALL)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_AGENT)
    organization = models.ForeignKey(
        "Organization", on_delete=models.CASCADE, null=True, blank=True, related_name="downloads"
    )

    def __str__(self):
        return self.label


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    wazuh_group = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        if not self.wazuh_group:
            self.wazuh_group = self.slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="org_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        unique_together = [("user", "organization")]

    def __str__(self):
        return f"{self.user} → {self.organization}"


class VulnerabilitySnapshot(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="vuln_snapshots"
    )
    date = models.DateField(default=timezone.now)
    critical = models.IntegerField(default=0)
    high = models.IntegerField(default=0)
    medium = models.IntegerField(default=0)
    low = models.IntegerField(default=0)
    new_count = models.IntegerField(default=0)
    resolved_count = models.IntegerField(default=0)
    cve_ids = models.JSONField(default=list)

    class Meta:
        unique_together = [("organization", "date")]

    def __str__(self):
        return f"{self.organization} snapshot {self.date}"


class WorkPackage(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="work_packages")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_work_packages"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org"],
                condition=models.Q(status="active"),
                name="unique_active_work_package_per_org",
            )
        ]

    def __str__(self):
        return f"{self.org} work package ({self.status}) {self.created_at:%Y-%m-%d}"


class WorkPackageItem(models.Model):
    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_LOW, "Low"),
    ]

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_ACCEPTED_RISK = "accepted_risk"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_ACCEPTED_RISK, "Accepted Risk"),
    ]

    work_package = models.ForeignKey(WorkPackage, on_delete=models.CASCADE, related_name="items")
    cve_id = models.CharField(max_length=50)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    cvss_score = models.FloatField()
    description = models.TextField()
    references = models.JSONField(default=list)
    affected_agent_count = models.IntegerField()
    impact_score = models.FloatField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    note = models.TextField(blank=True, default="")
    affected_agents = models.JSONField(default=list)

    def clean(self):
        if self.note and self.status != self.STATUS_ACCEPTED_RISK:
            raise ValidationError({"note": "Notes are only allowed when status is accepted_risk."})

    def __str__(self):
        return f"{self.cve_id} ({self.work_package})"
