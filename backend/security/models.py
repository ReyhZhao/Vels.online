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


# The single, dedicated home for Shared Infrastructure events (ADR-0017). Seeded
# idempotently by the data migration; never represents a paying tenant.
INFRASTRUCTURE_ORG_SLUG = "infrastructure"
INFRASTRUCTURE_ORG_NAME = "Shared Infrastructure"


class OrganizationQuerySet(models.QuerySet):
    def tenants(self):
        """Only real, agent-bound tenant orgs — excludes the Infrastructure org (ADR-0017)."""
        return self.filter(is_infrastructure=False)


class OrganizationManager(models.Manager.from_queryset(OrganizationQuerySet)):
    pass


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    wazuh_group = models.CharField(max_length=255)
    # ADR-0017: the Infrastructure org is a non-tenant pseudo-org that owns Shared
    # Infrastructure events (the firewall/reverse-proxy logged as the Wazuh manager,
    # agent.id="000"). It is excluded from every "real tenant" code path via
    # Organization.objects.tenants(); only Hunt scope resolution visits it.
    is_infrastructure = models.BooleanField(default=False)
    max_routes = models.PositiveIntegerField(null=True, blank=True)
    triage_fp_threshold = models.FloatField(default=0.95)
    # Minimum disposition_confidence (ADR-0024) the Classify phase must report before
    # the agentic Triage Work phase is allowed to run unattended. Conservative default
    # (high bar) so autonomy stays off until an operator deliberately tunes it down.
    triage_work_threshold = models.FloatField(default=0.95)
    triage_prompt_context = models.TextField(null=True, blank=True)
    alert_match_lookback_days = models.PositiveIntegerField(default=30)
    alert_auto_promote_threshold = models.PositiveIntegerField(default=5)
    alert_auto_promote_window_minutes = models.PositiveIntegerField(default=60)
    # IOC-extraction exclusions beyond registered Assets (#603). Indicators that
    # fall inside one of these CIDR ranges (membership) or that equal/are a
    # subdomain of one of these owned domains (suffix match) are dropped before
    # being saved as IOCs on the org's incidents. Both default to empty.
    internal_ip_ranges = models.JSONField(default=list, blank=True)
    owned_domains = models.JSONField(default=list, blank=True)
    llm_residual_autocreate_threshold = models.FloatField(null=True, blank=True)
    # IANA timezone name (e.g. "Europe/Amsterdam"). Used to interpret a Scheduled
    # Search Rule's time-of-day window in the owning org's local time (#440).
    timezone = models.CharField(max_length=64, default="UTC")
    # Live Attack Map (PRD #594, ADR-0027): the org's location, where its inbound
    # attack arcs land. Nullable — orgs without coordinates fall back to the
    # Infrastructure org's home/perimeter point. The Infrastructure org's own row
    # carries that home coordinate (ADR-0017).
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    objects = OrganizationManager()

    def save(self, *args, **kwargs):
        if not self.wazuh_group:
            self.wazuh_group = self.slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def get_infrastructure(cls):
        """Return the single Infrastructure org, creating it idempotently (ADR-0017)."""
        org, _ = cls.objects.get_or_create(
            is_infrastructure=True,
            defaults={
                "name": INFRASTRUCTURE_ORG_NAME,
                "slug": INFRASTRUCTURE_ORG_SLUG,
                "wazuh_group": "",
            },
        )
        return org


class OrganizationMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="org_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        unique_together = [("user", "organization")]

    def __str__(self):
        return f"{self.user} → {self.organization}"


class ServiceAccount(models.Model):
    """A non-human API principal (PRD #694): lets an admin connect external services
    without borrowing a person's account.

    Backed by a dedicated, non-interactive ``User`` (``is_staff=False`` /
    ``is_superuser=False``, unusable password, never provisioned via SSO) so it can
    never log in interactively and can never hold cross-org / staff-only SOC powers.
    Its org access is granted *solely* through ``OrganizationMembership`` rows, so the
    existing membership gate (``_resolve_org``) scopes its token automatically — no new
    enforcement path. It authenticates with a single DRF auth token
    (``rest_framework.authtoken``), one per account.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="service_account")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Auditing (#696): the most recent time the account's token authenticated a
    # request, and the client IP it came from. Only the latest use is kept — not a
    # full history. Recorded by ServiceAccountTokenAuthentication on every accepted
    # request (write-throttled; see record_use).
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    # Optional source-IP allowlist (#696): CIDR ranges / individual IPs the token may
    # be used from. Empty = unrestricted. When non-empty, a request whose (proxy-
    # derived) client IP is not covered is rejected at authentication time — and its
    # last-used fields are left untouched. Fails closed: a set allowlist with an
    # undeterminable client IP is denied.
    allowed_ips = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"ServiceAccount({self.name})"

    @classmethod
    def create(cls, *, name, description="", orgs=(), allowed_ips=(), created_by=None):
        """Provision the backing user, its org grants, and its token in one step."""
        import uuid

        from rest_framework.authtoken.models import Token

        username = f"svc-{uuid.uuid4().hex[:20]}"
        user = User.objects.create(
            username=username, is_active=True, is_staff=False, is_superuser=False
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        account = cls.objects.create(
            user=user,
            name=name,
            description=description,
            allowed_ips=list(allowed_ips),
            created_by=created_by,
        )
        account.set_orgs(orgs)
        Token.objects.create(user=user)
        return account

    def is_ip_allowed(self, ip):
        """True if ``ip`` may use this account's token.

        An empty allowlist permits everything. A non-empty allowlist fails closed:
        an unparseable/absent ``ip`` is denied. Malformed stored entries are skipped
        defensively (the write path validates, but a row could be edited out-of-band).
        """
        import ipaddress

        ranges = self.allowed_ips or []
        if not ranges:
            return True
        try:
            addr = ipaddress.ip_address((ip or "").strip())
        except ValueError:
            return False
        for entry in ranges:
            try:
                if addr in ipaddress.ip_network((entry or "").strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False

    def record_use(self, ip):
        """Stamp last-used time/IP for an accepted request.

        Write-throttled: an identical IP seen again within a minute is skipped, so a
        chatty token doesn't amplify into a DB write per request. A changed IP always
        records immediately, keeping the audit trail's source visibility crisp.
        """
        now = timezone.now()
        if (
            self.last_used_at is not None
            and self.last_used_ip == ip
            and (now - self.last_used_at).total_seconds() < 60
        ):
            return
        self.last_used_at = now
        self.last_used_ip = ip
        self.save(update_fields=["last_used_at", "last_used_ip"])

    def set_orgs(self, orgs):
        """Replace the account's org grants (memberships) with exactly ``orgs``."""
        desired = {o.pk: o for o in orgs}
        existing = {m.organization_id: m for m in self.user.org_memberships.all()}
        for org_id, membership in existing.items():
            if org_id not in desired:
                membership.delete()
        for org_id, org in desired.items():
            if org_id not in existing:
                OrganizationMembership.objects.create(user=self.user, organization=org)

    @property
    def orgs(self):
        return Organization.objects.filter(memberships__user=self.user).order_by("name")

    @property
    def token(self):
        from rest_framework.authtoken.models import Token

        return Token.objects.filter(user=self.user).first()

    def rotate_token(self):
        """Invalidate the current token and issue a fresh one."""
        from rest_framework.authtoken.models import Token

        Token.objects.filter(user=self.user).delete()
        return Token.objects.create(user=self.user)


class OrgInvitation(models.Model):
    ROLE_MEMBER = "member"
    ROLE_STAFF = "staff"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_MEMBER, "Member"),
        (ROLE_STAFF, "Staff"),
        (ROLE_ADMIN, "Admin"),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_EXPIRED, "Expired"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    authentik_invite_token = models.UUIDField(null=True, blank=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_invitations"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} → {self.organization} ({self.status})"


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


class CveAdvisory(models.Model):
    cve_id = models.CharField(max_length=50)
    platform = models.CharField(max_length=20)
    advisory_url = models.URLField(max_length=500, null=True, blank=True)
    remediation_text = models.TextField(null=True, blank=True)
    fetched_at = models.DateTimeField()
    raw_data = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [("cve_id", "platform")]

    def __str__(self):
        return f"{self.cve_id} ({self.platform})"


class RiskAcceptance(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="risk_acceptances")
    cve_id = models.CharField(max_length=50)
    accepted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="risk_acceptances"
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=20, blank=True, default="")
    cvss_score = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = [("org", "cve_id")]

    def __str__(self):
        return f"{self.cve_id} accepted for {self.org}"
