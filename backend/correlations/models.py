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


class DetectionSuggestion(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    organization = models.ForeignKey(
        "security.Organization",
        on_delete=models.CASCADE,
        related_name="detection_suggestions",
    )
    proposed_alerts = models.ManyToManyField(
        "alerts.Alert",
        related_name="detection_suggestions",
        blank=True,
    )
    rationale = models.TextField()
    confidence = models.FloatField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detection_suggestion",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"DetectionSuggestion {self.id} ({self.status}) for {self.organization}"


class SystemRuleMute(models.Model):
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="system_rule_mutes"
    )
    rule = models.ForeignKey(
        CorrelationRule, on_delete=models.CASCADE, related_name="mutes"
    )

    class Meta:
        unique_together = [("organization", "rule")]


# ── Scheduled Search Rules ────────────────────────────────────────────────────

SEARCH_OPERATOR_EQUALS = "equals"
SEARCH_OPERATOR_CONTAINS = "contains"
SEARCH_OPERATOR_GTE = "gte"
SEARCH_OPERATOR_LTE = "lte"
SEARCH_OPERATOR_CIDR = "cidr"

SEARCH_OPERATOR_CHOICES = [
    (SEARCH_OPERATOR_EQUALS, "Equals"),
    (SEARCH_OPERATOR_CONTAINS, "Contains"),
    (SEARCH_OPERATOR_GTE, ">="),
    (SEARCH_OPERATOR_LTE, "<="),
    (SEARCH_OPERATOR_CIDR, "IP in CIDR"),
]

_MAX_FINDINGS_DEFAULT = 50
_MIN_INTERVAL_MINUTES = 5


class SearchRuleMute(models.Model):
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="search_rule_mutes"
    )
    rule = models.ForeignKey(
        "SearchRule", on_delete=models.CASCADE, related_name="mutes"
    )

    class Meta:
        unique_together = [("organization", "rule")]

    def __str__(self):
        return f"{self.organization} mutes search rule {self.rule_id}"


class SearchRule(models.Model):
    organization = models.ForeignKey(
        "security.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_rules",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="medium")
    correlation_key = models.CharField(
        max_length=50, choices=CORRELATION_KEY_CHOICES, default=CORRELATION_KEY_NONE
    )
    window_minutes = models.PositiveIntegerField(default=60)
    interval_minutes = models.PositiveIntegerField(default=60)
    max_findings_per_run = models.PositiveIntegerField(default=_MAX_FINDINGS_DEFAULT)
    include_agentless = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SearchRuleLeg(models.Model):
    rule = models.ForeignKey(SearchRule, on_delete=models.CASCADE, related_name="legs")
    count = models.PositiveIntegerField(default=1)
    display_order = models.PositiveIntegerField(default=0)
    # Diversity Constraint (ADR-0009): when distinct_field is set, this leg is satisfied
    # for a correlation key only when its matching docs span at least min_distinct distinct
    # values of distinct_field (in addition to doc_count >= count). Empty = no constraint.
    distinct_field = models.CharField(max_length=200, blank=True, default="")
    min_distinct = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"Leg {self.display_order} of {self.rule}"

    @property
    def has_diversity(self) -> bool:
        """True when this leg carries an active Diversity Constraint."""
        return bool(self.distinct_field)


class SearchLegCondition(models.Model):
    leg = models.ForeignKey(SearchRuleLeg, on_delete=models.CASCADE, related_name="conditions")
    field_name = models.CharField(max_length=200)
    operator = models.CharField(max_length=10, choices=SEARCH_OPERATOR_CHOICES)
    value = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.field_name} {self.operator} {self.value!r}"


class SearchFiring(models.Model):
    rule = models.ForeignKey(SearchRule, on_delete=models.CASCADE, related_name="firings")
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="search_firings"
    )
    key_value = models.CharField(max_length=500, default="none")
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.SET_NULL, null=True, related_name="search_firings"
    )
    finding_count = models.PositiveIntegerField(default=0)
    fired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fired_at"]

    def __str__(self):
        return f"{self.rule} fired at {self.fired_at} ({self.finding_count} findings)"


class SearchFinding(models.Model):
    rule = models.ForeignKey(SearchRule, on_delete=models.CASCADE, related_name="findings")
    alert = models.ForeignKey(
        "alerts.Alert", on_delete=models.CASCADE, related_name="search_findings"
    )
    source_index = models.CharField(max_length=200)
    wazuh_doc_id = models.CharField(max_length=200)
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("rule", "source_index", "wazuh_doc_id")]
        ordering = ["-found_at"]

    def __str__(self):
        return f"Finding {self.wazuh_doc_id} for {self.rule}"
