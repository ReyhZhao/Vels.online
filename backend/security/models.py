from django.contrib.auth.models import User
from django.db import models


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
