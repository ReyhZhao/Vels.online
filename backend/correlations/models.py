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

# Time-of-day window modes (#440): consider only documents inside, or only outside, the window.
TIME_WINDOW_MODE_INSIDE = "inside"
TIME_WINDOW_MODE_OUTSIDE = "outside"
TIME_WINDOW_MODE_CHOICES = [
    (TIME_WINDOW_MODE_INSIDE, "Inside window"),
    (TIME_WINDOW_MODE_OUTSIDE, "Outside window"),
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

# Leg-level document-count threshold operator (#519, ADR-0020). Distinct from the
# field-level SEARCH_OPERATOR_* condition operators above: this governs how a Leg's
# matched-document count is compared with its `count` threshold. `lte` expresses an
# Absence Firing ("at most N matched", e.g. ≤ 0 = "no documents at all").
SEARCH_COUNT_OP_GTE = "gte"
SEARCH_COUNT_OP_LTE = "lte"

SEARCH_COUNT_OP_CHOICES = [
    (SEARCH_COUNT_OP_GTE, "At least (≥)"),
    (SEARCH_COUNT_OP_LTE, "At most (≤)"),
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
    # Optional rule-level time-of-day window (#440). When all of start/end/days are set,
    # the rule only considers documents whose org-local timestamp falls inside (or outside,
    # per mode) the window on the selected days. Days are ISO weekdays (1=Mon … 7=Sun).
    # Unset (any of start/end/days empty) = no constraint (current behaviour).
    time_window_start = models.TimeField(null=True, blank=True)
    time_window_end = models.TimeField(null=True, blank=True)
    time_window_days = models.JSONField(default=list, blank=True)
    time_window_mode = models.CharField(
        max_length=10, choices=TIME_WINDOW_MODE_CHOICES, default=TIME_WINDOW_MODE_INSIDE, blank=True
    )
    # Novelty Constraint baseline depth (ADR-0021): how far back history is consulted to
    # decide whether a leg's novelty_field value is "new". Sibling of window_minutes — the
    # rule owns *time*, the leg owns *what* is watched. Days, because baselines are
    # intrinsically days/weeks. Setting this to the index retention ceiling yields the
    # "first time ever" variant.
    baseline_lookback_days = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def has_time_window(self) -> bool:
        """True when this rule carries an active time-of-day window (#440)."""
        return bool(self.time_window_start and self.time_window_end and self.time_window_days)


class SearchRuleLeg(models.Model):
    rule = models.ForeignKey(SearchRule, on_delete=models.CASCADE, related_name="legs")
    count = models.PositiveIntegerField(default=1)
    # Count Operator (#519, ADR-0020): how `count` is compared with the matched-document
    # count. `gte` (default) is the ordinary "at least N matched"; `lte` is an Absence
    # Firing ("at most N matched", e.g. ≤ 0 = "no documents in the window").
    count_operator = models.CharField(
        max_length=3, choices=SEARCH_COUNT_OP_CHOICES, default=SEARCH_COUNT_OP_GTE
    )
    display_order = models.PositiveIntegerField(default=0)
    # Diversity Constraint (ADR-0009): when distinct_field is set, this leg is satisfied
    # for a correlation key only when its matching docs span at least min_distinct distinct
    # values of distinct_field (in addition to doc_count >= count). Empty = no constraint.
    distinct_field = models.CharField(max_length=200, blank=True, default="")
    min_distinct = models.PositiveIntegerField(default=1)
    # Novelty Constraint (ADR-0021): when novelty_field is set, this leg fires for a
    # correlation key only when a matching document carries a value of novelty_field whose
    # *earliest* occurrence within the rule's baseline lookback lands inside the detection
    # boundary (the run interval). The baseline-comparing sibling of distinct_field. A raw
    # Wazuh field path (resolved via .keyword), e.g. agent.name. Empty = no constraint.
    novelty_field = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"Leg {self.display_order} of {self.rule}"

    @property
    def has_diversity(self) -> bool:
        """True when this leg carries an active Diversity Constraint."""
        return bool(self.distinct_field)

    @property
    def has_novelty(self) -> bool:
        """True when this leg carries an active Novelty Constraint (ADR-0021)."""
        return bool(self.novelty_field)

    @property
    def is_absence(self) -> bool:
        """True when this leg triggers an Absence Firing (count_operator = lte)."""
        return self.count_operator == SEARCH_COUNT_OP_LTE


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


# Rule Test last-run statuses (PRD #439, ADR-0010).
TEST_STATUS_NEVER = "never"
TEST_STATUS_PASS = "pass"
TEST_STATUS_FAIL = "fail"
TEST_STATUS_ERROR = "error"
TEST_STATUS_CHOICES = [
    (TEST_STATUS_NEVER, "Never run"),
    (TEST_STATUS_PASS, "Pass"),
    (TEST_STATUS_FAIL, "Fail"),
    (TEST_STATUS_ERROR, "Error"),
]


class SearchRuleTest(models.Model):
    """A detection-as-code Rule Test on a Scheduled Search Rule (PRD #439, ADR-0010).

    Bundles a set of synthetic Sample Documents (partial raw Wazuh docs, stored as an
    opaque JSON list) with a whole-rule fire/no-fire Expectation. Run on demand against
    an ephemeral OpenSearch index using the real matcher; the last result is summarised
    inline. Samples are a JSON blob, not a child table (an unordered set fed together).
    """
    rule = models.ForeignKey(SearchRule, on_delete=models.CASCADE, related_name="tests")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    expect_fire = models.BooleanField(default=True)
    samples = models.JSONField(default=list)  # list of partial raw Wazuh docs
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=10, choices=TEST_STATUS_CHOICES, default=TEST_STATUS_NEVER
    )
    last_diagnostics = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Test {self.name!r} for {self.rule}"
