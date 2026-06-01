from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class WazuhActiveResponse(models.Model):
    name = models.CharField(max_length=255)
    command = models.CharField(max_length=255)
    platforms = models.JSONField(default=list)
    default_args = models.TextField(blank=True, default="")
    timeout = models.PositiveIntegerField(default=0)
    available_in_security_overview = models.BooleanField(default=False)
    requires_confirmation = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="wazuh_active_responses"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Automation(models.Model):
    name = models.CharField(max_length=255)
    semaphore_template_id = models.IntegerField()
    semaphore_template_name = models.CharField(max_length=255, blank=True)
    default_vars = models.TextField(null=True, blank=True)
    incident_var_mappings = models.TextField(null=True, blank=True)
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="automations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
