from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


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
