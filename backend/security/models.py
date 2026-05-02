from django.contrib.auth.models import User
from django.db import models


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
