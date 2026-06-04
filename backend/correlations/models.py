from django.db import models


CORRELATION_KEY_HOST = "host.name"
CORRELATION_KEY_SOURCE_IP = "source.ip"
CORRELATION_KEY_USERNAME = "user.name"
CORRELATION_KEY_FILE_HASH = "file.hash.sha256"
CORRELATION_KEY_PROCESS = "process.name"
CORRELATION_KEY_NONE = "none"

CORRELATION_KEY_CHOICES = [
    (CORRELATION_KEY_HOST, "Host (host.name)"),
    (CORRELATION_KEY_SOURCE_IP, "Source IP (source.ip)"),
    (CORRELATION_KEY_USERNAME, "Username (user.name)"),
    (CORRELATION_KEY_FILE_HASH, "File Hash (file.hash.sha256)"),
    (CORRELATION_KEY_PROCESS, "Process (process.name)"),
    (CORRELATION_KEY_NONE, "None (org-wide)"),
]

SEVERITY_CHOICES = [
    ("critical", "Critical"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("info", "Info"),
]

OPERATOR_EQUALS = "equals"
OPERATOR_IN = "in"
OPERATOR_CONTAINS = "contains"
OPERATOR_GTE = "gte"
OPERATOR_LTE = "lte"
OPERATOR_CIDR = "cidr"

OPERATOR_CHOICES = [
    (OPERATOR_EQUALS, "Equals"),
    (OPERATOR_IN, "In"),
    (OPERATOR_CONTAINS, "Contains"),
    (OPERATOR_GTE, "Severity >="),
    (OPERATOR_LTE, "Severity <="),
    (OPERATOR_CIDR, "IP in CIDR"),
]

FIELD_KIND_ALERT = "alert_field"
FIELD_KIND_ENTITY = "entity"
FIELD_KIND_SOURCE_REF = "source_ref"

FIELD_KIND_CHOICES = [
    (FIELD_KIND_ALERT, "Alert field"),
    (FIELD_KIND_ENTITY, "ECS entity"),
    (FIELD_KIND_SOURCE_REF, "Source ref key"),
]

ALERT_FIELD_CATALOG = frozenset({"severity", "title", "description", "source_kind", "pap", "tlp"})
ENTITY_CATALOG = frozenset({"host.name", "source.ip", "user.name", "file.hash.sha256", "process.name"})
SOURCE_REF_CATALOG = frozenset({"rule_id", "rule_description", "level", "cve_id"})


class CorrelationRule(models.Model):
    organization = models.ForeignKey(
        "security.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="correlation_rules",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    correlation_key = models.CharField(
        max_length=50, choices=CORRELATION_KEY_CHOICES, default=CORRELATION_KEY_NONE
    )
    window_minutes = models.PositiveIntegerField(default=60)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="medium")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CorrelationRuleLeg(models.Model):
    rule = models.ForeignKey(CorrelationRule, on_delete=models.CASCADE, related_name="legs")
    count = models.PositiveIntegerField(default=1)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"Leg {self.display_order} of {self.rule}"


class LegCondition(models.Model):
    leg = models.ForeignKey(CorrelationRuleLeg, on_delete=models.CASCADE, related_name="conditions")
    field_kind = models.CharField(max_length=20, choices=FIELD_KIND_CHOICES)
    field_name = models.CharField(max_length=100)
    operator = models.CharField(max_length=10, choices=OPERATOR_CHOICES)
    value = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.field_kind}.{self.field_name} {self.operator} {self.value!r}"


class CorrelationFiring(models.Model):
    rule = models.ForeignKey(CorrelationRule, on_delete=models.CASCADE, related_name="firings")
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="correlation_firings"
    )
    entity_value = models.CharField(max_length=500, default="none")
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.SET_NULL, null=True, related_name="correlation_firings"
    )
    fired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fired_at"]

    def __str__(self):
        return f"{self.rule} fired at {self.fired_at}"


class SystemRuleMute(models.Model):
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="system_rule_mutes"
    )
    rule = models.ForeignKey(
        CorrelationRule, on_delete=models.CASCADE, related_name="mutes"
    )

    class Meta:
        unique_together = [("organization", "rule")]

    def __str__(self):
        return f"{self.organization} mutes {self.rule}"
