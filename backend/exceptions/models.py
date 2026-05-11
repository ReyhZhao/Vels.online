from django.contrib.auth.models import User
from django.db import models


class ExceptionRule(models.Model):
    FIELD_TYPE_CHOICES = [("pcre2", "PCRE2"), ("literal", "Literal")]
    SCOPE_CHOICES      = [("org", "Organisation"), ("global", "Global")]
    STATUS_CHOICES     = [("pending", "Pending"), ("applied", "Applied"), ("disabled", "Disabled")]

    wazuh_rule_id  = models.IntegerField(unique=True, null=True, blank=True)
    trigger_rule_id = models.IntegerField(null=True, blank=True)
    description    = models.TextField(blank=True, default="")
    match_value    = models.CharField(max_length=512, blank=True, default="")
    field_name     = models.CharField(max_length=255, blank=True, default="")
    field_value    = models.CharField(max_length=512, blank=True, default="")
    field_type     = models.CharField(max_length=10, choices=FIELD_TYPE_CHOICES, default="literal")
    scope          = models.CharField(max_length=10, choices=SCOPE_CHOICES, default="org")
    agent_name     = models.CharField(max_length=255, blank=True, default="")
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    organisation = models.ForeignKey(
        "security.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exception_rules",
    )
    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exception_rules",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exception_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ExceptionRule #{self.wazuh_rule_id or 'unassigned'}: {self.description[:50]}"


class WazuhRuleIdPool(models.Model):
    POOL_MIN = 200000
    POOL_MAX = 209999

    # Seed value is POOL_MIN - 1 so the first allocation returns POOL_MIN.
    last_assigned_id = models.IntegerField(default=POOL_MIN - 1)

    class Meta:
        verbose_name = "Wazuh Rule ID Pool"

    def __str__(self):
        return f"WazuhRuleIdPool (last={self.last_assigned_id})"


class FreedRuleId(models.Model):
    rule_id  = models.IntegerField(unique=True)
    freed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rule_id"]

    def __str__(self):
        return f"FreedRuleId({self.rule_id})"
