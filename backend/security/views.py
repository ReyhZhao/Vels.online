import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.response import Response
from rest_framework.views import APIView
from signups.authentik import AuthentikAPIError, AuthentikClient

logger = logging.getLogger(__name__)

from django.db.models import Count, Q
from security.models import Download, OrgInvitation, Organization, OrganizationMembership, RiskAcceptance, ServiceAccount, VulnerabilitySnapshot, WorkPackage, WorkPackageItem
from security.serializers import (
    AgentSerializer,
    CveDetailSerializer,
    DownloadCreateSerializer,
    DownloadSerializer,
    EnrollmentSerializer,
    FleetVulnerabilitiesResponseSerializer,
    OrganizationSerializer,
    PaginatedEventsSerializer,
    PaginatedVulnerabilitiesSerializer,
    RiskAcceptanceSerializer,
    ServiceAccountSerializer,
    VulnerabilitySnapshotSerializer,
    WorkPackageArchiveListSerializer,
    WorkPackageItemSerializer,
    WorkPackageItemUpdateSerializer,
    WorkPackageSerializer,
)
from security.advisory import get_or_fetch as get_or_fetch_advisory, normalize_platform
from security.storage import StorageClient
from security.work_package_service import add_more_items, generate_work_package
from security.opensearch import OpenSearchClient, OpenSearchError
from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

_CACHE_TTL = 60           # seconds — dashboard / agents
_EVENTS_CACHE_TTL = 300   # seconds — per-agent events (5 min)
_VULNS_CACHE_TTL = 3600   # seconds — per-agent vulnerabilities (1 hr)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _generate_slug(name):
    base = slugify(name)
    slug = base
    n = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _dashboard_cache_key(slug):
    return f"security_dashboard_{slug}"


def _agents_cache_key(slug):
    return f"security_agents_{slug}"


def _events_cache_key(agent_id, org_slug, hours=24, severity=None, search=""):
    sev_part = ",".join(sorted(severity)) if severity else ""
    search_part = search.replace(" ", "+")
    return f"security_events_{agent_id}_{org_slug}_{hours}_{sev_part}_{search_part}"


def _fleet_events_cache_key(org_slug, minutes=1440, severity=None, search="", agent_filter="", offset=0):
    sev_part = ",".join(sorted(severity)) if severity else ""
    search_part = search.replace(" ", "+")
    return f"security_fleet_events_{org_slug}_{minutes}_{sev_part}_{search_part}_{agent_filter}_{offset}"


def _vulns_cache_key(agent_id, org_slug, severity=None, fix_available=None, search=""):
    sev_part = ",".join(sorted(severity)) if severity else ""
    fix_part = "1" if fix_available else ""
    search_part = search.replace(" ", "+")
    return f"security_vulns_{agent_id}_{org_slug}_{sev_part}_{fix_part}_{search_part}"


def _serialize_agent(agent):
    os_info = agent.get("os", {})
    if isinstance(os_info, dict):
        os_label = f"{os_info.get('name', '')} {os_info.get('version', '')}".strip() or os_info.get("platform", "")
        os_platform = os_info.get("platform", "")
    else:
        os_label = ""
        os_platform = ""
    return {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "ip": agent.get("ip"),
        "status": agent.get("status"),
        "os": os_label,
        "os_platform": os_platform,
        "last_seen": agent.get("lastKeepAlive"),
    }


def _event_severity(level):
    if level >= 12:
        return "critical"
    if level >= 8:
        return "high"
    if level >= 4:
        return "medium"
    return "low"


def _serialize_event(event):
    rule = event.get("rule", {})
    agent = event.get("agent", {})
    level = rule.get("level", 0)
    return {
        "id": event.get("_id", ""),
        "timestamp": event.get("@timestamp") or event.get("timestamp"),
        "rule_description": rule.get("description", ""),
        "rule_id": rule.get("id", ""),
        "level": level,
        "severity": _event_severity(level),
        "agent_id": str(agent.get("id", "")),
        "agent_name": agent.get("name", ""),
    }


def _serialize_event_detail(event):
    rule = event.get("rule", {})
    agent = event.get("agent", {})
    mitre = rule.get("mitre", {})
    data_fields = event.get("data", {})

    detail = {
        "id": event.get("_id", ""),
        "timestamp": event.get("@timestamp") or event.get("timestamp"),
        "severity": _event_severity(rule.get("level", 0)),
        "rule_description": rule.get("description", ""),
        "rule_id": rule.get("id", ""),
        "level": rule.get("level", 0),
        "rule_groups": rule.get("groups", []),
        "agent_name": agent.get("name", ""),
        "agent_ip": agent.get("ip", ""),
        "log_source": event.get("location", ""),
        "raw_log": event.get("full_log", ""),
    }

    mitre_data = {}
    tactic = mitre.get("tactic")
    technique = mitre.get("technique")
    technique_id = mitre.get("id")
    if tactic:
        mitre_data["tactic"] = tactic if isinstance(tactic, list) else [tactic]
    if technique:
        mitre_data["technique"] = technique if isinstance(technique, list) else [technique]
    if technique_id:
        mitre_data["technique_id"] = technique_id if isinstance(technique_id, list) else [technique_id]
    if mitre_data:
        detail["mitre"] = mitre_data

    network_data = {}
    if data_fields.get("srcip"):
        network_data["src_ip"] = data_fields["srcip"]
    if data_fields.get("dstip"):
        network_data["dst_ip"] = data_fields["dstip"]
    if data_fields.get("protocol"):
        network_data["protocol"] = data_fields["protocol"]
    if network_data:
        detail["network"] = network_data

    return detail


def _serialize_vulnerability(vuln):
    v = vuln.get("vulnerability", {})
    pkg = vuln.get("package", {})
    return {
        "id": vuln.get("_id", ""),
        "cve": v.get("id", ""),
        "package": pkg.get("name", ""),
        "version": pkg.get("version", ""),
        "severity": v.get("severity", "").lower(),
        "fix_available": v.get("status", "").lower() == "fixed",
    }


def _serialize_vulnerability_detail(vuln):
    v = vuln.get("vulnerability", {})
    pkg = vuln.get("package", {})
    cvss = v.get("cvss", {})
    cvss3 = cvss.get("cvss3", {})

    detail = {
        "id": vuln.get("_id", ""),
        "cve": v.get("id", ""),
        "severity": v.get("severity", "").lower(),
        "cvss_score": cvss3.get("base_score"),
        "package": pkg.get("name", ""),
        "installed_version": pkg.get("version", ""),
        "fixed_version": pkg.get("fixed_version", "") or None,
        "description": v.get("description", ""),
        "published": v.get("published", "") or None,
    }

    refs = v.get("references", [])
    if refs:
        detail["references"] = refs if isinstance(refs, list) else [refs]

    return detail


def _resolve_org(request, slug):
    """Validates slug and checks the requesting user has access. Returns (org, error_response)."""
    if not slug:
        return None, Response({"detail": "org is required."}, status=400)
    try:
        org = Organization.objects.get(slug=slug)
    except Organization.DoesNotExist:
        return None, Response(status=404)
    if not request.user.is_staff:
        if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
            return None, Response(status=403)
    return org, None


def _resolve_agent(request, org, agent_id):
    """Checks that agent_id belongs to org. Staff users are exempt. Returns error_response or None."""
    if request.user.is_staff:
        return None
    cache_key = _agents_cache_key(org.slug)
    cached = cache.get(cache_key)
    if cached is not None:
        agent_ids = {str(a["id"]) for a in cached}
    else:
        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("Wazuh error in _resolve_agent for agent_id=%s", agent_id)
            return Response({"detail": "Security service unavailable."}, status=502)
        agent_ids = {str(a.get("id")) for a in raw_agents}
    if str(agent_id) not in agent_ids:
        return Response(status=403)
    return None


class OrganizationListView(APIView):
    def get(self, request):
        if request.user.is_staff:
            # Tenants-only by default so the Infrastructure pseudo-org (ADR-0017) stays
            # out of incident-assignment / tenant-management pickers. The Hunt scope
            # picker opts in with ?include_infrastructure=1 to offer it as a target.
            include_infra = request.query_params.get("include_infrastructure") in ("1", "true")
            qs = Organization.objects.all() if include_infra else Organization.objects.tenants()
            orgs = qs.order_by("name")
        else:
            orgs = Organization.objects.filter(
                memberships__user=request.user
            ).order_by("name")
        return Response(OrganizationSerializer(orgs, many=True).data)

    def post(self, request):
        if not request.user.is_staff:
            return Response(status=403)

        name = request.data.get("name", "").strip()
        if not name:
            return Response({"detail": "name is required."}, status=400)

        slug = _generate_slug(name)

        try:
            with transaction.atomic():
                org = Organization.objects.create(name=name, slug=slug)
                WazuhClient().create_group(org.wazuh_group)
        except (WazuhAPIError, WazuhAuthError) as exc:
            logger.exception("Wazuh error creating group for org slug=%s", slug)
            return Response({"detail": "Failed to create Wazuh group."}, status=400)

        return Response(OrganizationSerializer(org).data, status=201)


class OrganizationDetailView(APIView):
    def _get_org(self, request, slug):
        if request.user.is_staff:
            return Organization.objects.filter(slug=slug).first()
        return Organization.objects.filter(
            slug=slug, memberships__user=request.user
        ).first()

    def get(self, request, slug):
        org = self._get_org(request, slug)
        if org is None:
            return Response(status=404)
        return Response(OrganizationSerializer(org).data)

    def patch(self, request, slug):
        if not request.user.is_staff:
            return Response(status=403)
        org = Organization.objects.filter(slug=slug).first()
        if org is None:
            return Response(status=404)
        serializer = OrganizationSerializer(org, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        serializer.save()
        return Response(serializer.data)


class OrgInviteView(APIView):
    """POST /api/security/organizations/<slug>/invite/ — send an invite to join an existing org."""

    def get(self, request, slug):
        if not request.user.is_staff:
            return Response(status=403)
        try:
            org = Organization.objects.get(slug=slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organisation not found."}, status=404)
        invitations = OrgInvitation.objects.filter(organization=org).order_by("-created_at")
        data = [
            {
                "id": inv.id,
                "email": inv.email,
                "full_name": inv.full_name,
                "role": inv.role,
                "status": inv.status,
                "invite_expires_at": inv.invite_expires_at,
                "created_at": inv.created_at,
            }
            for inv in invitations
        ]
        return Response(data)

    def post(self, request, slug):
        if not request.user.is_staff:
            return Response(status=403)
        try:
            org = Organization.objects.get(slug=slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organisation not found."}, status=404)

        email = request.data.get("email", "").strip().lower()
        full_name = request.data.get("full_name", "").strip()
        role = request.data.get("role", OrgInvitation.ROLE_MEMBER)

        if not email:
            return Response({"detail": "email is required."}, status=400)
        if not full_name:
            return Response({"detail": "full_name is required."}, status=400)
        if role not in (OrgInvitation.ROLE_MEMBER, OrgInvitation.ROLE_STAFF, OrgInvitation.ROLE_ADMIN):
            return Response({"detail": "role must be member, staff, or admin."}, status=400)

        from datetime import timedelta

        client = AuthentikClient()
        flow_slug = settings.AUTHENTIK_ENROLLMENT_FLOW_SLUG

        # Find or create the Authentik group for this org
        group_name = f"customer:{org.slug}"
        try:
            group_pk = client.find_group_by_name(group_name)
            if not group_pk:
                group_pk = client.create_group(group_name)
        except AuthentikAPIError as exc:
            logger.exception("Authentik error resolving group for org=%s", org.slug)
            return Response({"detail": "Failed to resolve Authentik group."}, status=502)

        # Resolve the enrollment flow UUID
        try:
            flow_uuid = client.get_flow_uuid(flow_slug)
        except AuthentikAPIError as exc:
            logger.exception("Authentik error resolving enrollment flow for org=%s", org.slug)
            return Response({"detail": "Failed to resolve enrollment flow."}, status=502)

        # Create an Authentik invitation
        expires_at = timezone.now() + timedelta(days=7)
        try:
            invitation = client.create_invitation(flow_uuid, expires_at, name=f"org-invite-{org.slug}-{slugify(email)}")
        except AuthentikAPIError as exc:
            logger.exception("Authentik error creating invitation for org=%s email=%s", org.slug, email)
            return Response({"detail": "Failed to create invitation."}, status=502)

        inv = OrgInvitation.objects.create(
            organization=org,
            email=email,
            full_name=full_name,
            role=role,
            authentik_invite_token=invitation["token"],
            invite_expires_at=expires_at,
            invited_by=request.user,
        )

        from security.tasks import send_org_invite_email
        send_org_invite_email.delay(inv.pk)

        return Response(
            {
                "id": inv.id,
                "email": inv.email,
                "full_name": inv.full_name,
                "role": inv.role,
                "status": inv.status,
                "invite_expires_at": inv.invite_expires_at,
                "created_at": inv.created_at,
            },
            status=201,
        )


def _validate_org_slugs(org_slugs):
    """Resolve a list of org slugs to Organizations, or return (None, error_response)."""
    if not isinstance(org_slugs, list):
        return None, Response({"detail": "org_slugs must be a list."}, status=400)
    orgs = list(Organization.objects.filter(slug__in=org_slugs))
    found = {o.slug for o in orgs}
    missing = [s for s in org_slugs if s not in found]
    if missing:
        return None, Response({"detail": f"Unknown organisation(s): {', '.join(missing)}."}, status=400)
    return orgs, None


def _validate_allowed_ips(value):
    """Normalise a service account's source-IP allowlist (#696), or return an error.

    Accepts individual IPs and CIDR ranges (IPv4/IPv6), normalising each to its
    network form — mirroring the org internal-ranges validation. Returns
    ``(cleaned_list, None)`` or ``(None, error_response)``.
    """
    import ipaddress

    if not isinstance(value, list):
        return None, Response({"detail": "allowed_ips must be a list."}, status=400)
    cleaned = []
    for entry in value:
        entry = (entry or "").strip()
        if not entry:
            continue
        try:
            # strict=False so a host-bit-set CIDR like 10.0.0.5/24 is accepted and
            # normalised to its network address.
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            return None, Response({"detail": f"Invalid IP or CIDR range: {entry!r}"}, status=400)
        cleaned.append(str(network))
    return cleaned, None


class ServiceAccountListView(APIView):
    """Staff-only management of service accounts (PRD #694).

    GET  — list all service accounts (name, granted orgs, creator, created-at).
    POST — create one from {name, description?, org_slugs: [...]}, returning the
           token exactly once.
    """

    def get(self, request):
        if not request.user.is_staff:
            return Response(status=403)
        accounts = ServiceAccount.objects.select_related("created_by").all()
        return Response(ServiceAccountSerializer(accounts, many=True).data)

    def post(self, request):
        if not request.user.is_staff:
            return Response(status=403)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required."}, status=400)
        description = (request.data.get("description") or "").strip()
        orgs, err = _validate_org_slugs(request.data.get("org_slugs") or [])
        if err:
            return err
        allowed_ips, err = _validate_allowed_ips(request.data.get("allowed_ips") or [])
        if err:
            return err
        account = ServiceAccount.create(
            name=name,
            description=description,
            orgs=orgs,
            allowed_ips=allowed_ips,
            created_by=request.user,
        )
        data = ServiceAccountSerializer(account).data
        # The full token is surfaced once, at creation. It is never redisplayed by
        # the list endpoint — rotate to obtain a fresh value if it is lost.
        data["token"] = account.token.key
        return Response(data, status=201)


class ServiceAccountDetailView(APIView):
    """Staff-only edit (name/description/org grants) and revoke of a service account."""

    def patch(self, request, pk):
        if not request.user.is_staff:
            return Response(status=403)
        account = ServiceAccount.objects.filter(pk=pk).first()
        if account is None:
            return Response(status=404)
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                return Response({"detail": "name is required."}, status=400)
            account.name = name
        if "description" in request.data:
            account.description = (request.data.get("description") or "").strip()
        if "allowed_ips" in request.data:
            allowed_ips, err = _validate_allowed_ips(request.data.get("allowed_ips") or [])
            if err:
                return err
            account.allowed_ips = allowed_ips
        account.save()
        if "org_slugs" in request.data:
            orgs, err = _validate_org_slugs(request.data.get("org_slugs") or [])
            if err:
                return err
            account.set_orgs(orgs)
        return Response(ServiceAccountSerializer(account).data)

    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(status=403)
        account = ServiceAccount.objects.filter(pk=pk).first()
        if account is None:
            return Response(status=404)
        # Deleting the backing user cascades to the account, its memberships, and its
        # token — so the token stops authenticating immediately.
        account.user.delete()
        return Response(status=204)


class ServiceAccountRotateTokenView(APIView):
    """Staff-only token rotation: invalidate the old token, return a new one once."""

    def post(self, request, pk):
        if not request.user.is_staff:
            return Response(status=403)
        account = ServiceAccount.objects.filter(pk=pk).first()
        if account is None:
            return Response(status=404)
        token = account.rotate_token()
        return Response({"token": token.key})


class AgentListView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        cache_key = _agents_cache_key(org.slug)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("Wazuh error in AgentListView for org=%s", org.slug)
            return Response({"detail": "Security service unavailable."}, status=502)

        data = AgentSerializer([_serialize_agent(a) for a in raw_agents], many=True).data
        cache.set(cache_key, data, _CACHE_TTL)
        return Response(data)


class DashboardView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        cache_key = _dashboard_cache_key(org.slug)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("Wazuh error in DashboardView")
            return Response({"detail": "Security service unavailable."}, status=502)

        try:
            os_client = OpenSearchClient()
            vuln_summary = os_client.get_vulnerabilities_summary(raw_agents)
            event_count = os_client.get_events_count(raw_agents)
        except OpenSearchError:
            vuln_summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            event_count = 0

        active = sum(1 for a in raw_agents if a.get("status") == "active")
        data = {
            "agent_count": len(raw_agents),
            "active_count": active,
            "vulnerabilities": vuln_summary,
            "events_24h": event_count,
        }
        cache.set(cache_key, data, _CACHE_TTL)
        return Response(data)


class SecurityRefreshView(APIView):
    def post(self, request):
        slug = request.data.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        cache.delete(_dashboard_cache_key(org.slug))
        cache.delete(_agents_cache_key(org.slug))

        agent_id = request.data.get("agent_id", "").strip()
        if agent_id:
            cache.delete(_events_cache_key(agent_id, org.slug))
            cache.delete(_vulns_cache_key(agent_id, org.slug))

        return Response({"detail": "Cache cleared."})


class AgentEventsView(APIView):
    def get(self, request, agent_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        err = _resolve_agent(request, org, agent_id)
        if err:
            return err

        severity_raw = request.query_params.get("severity", "").strip()
        severity = [s.strip() for s in severity_raw.split(",") if s.strip()] or None
        search = request.query_params.get("search", "").strip()
        try:
            hours = int(request.query_params.get("hours", 24))
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            return Response({"detail": "hours, offset and limit must be integers."}, status=400)

        is_first_page = offset == 0 and limit == 100
        cache_key = _events_cache_key(agent_id, org.slug, hours=hours, severity=severity, search=search)

        if is_first_page:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            result = OpenSearchClient().get_agent_events(
                agent_id, hours=hours, offset=offset, limit=limit,
                severity=severity, search=search,
            )
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in AgentEventsView")
            return Response({"detail": "Search service unavailable."}, status=502)

        data = PaginatedEventsSerializer({
            "events": [_serialize_event(e) for e in result["events"]],
            "total": result["total"],
        }).data

        if is_first_page:
            cache.set(cache_key, data, _EVENTS_CACHE_TTL)

        return Response(data)


class AgentEventDetailView(APIView):
    def get(self, request, agent_id, event_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        err = _resolve_agent(request, org, agent_id)
        if err:
            return err

        try:
            event = OpenSearchClient().get_event_by_id(agent_id, event_id)
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in AgentEventDetailView")
            return Response({"detail": "Search service unavailable."}, status=502)

        if event is None:
            return Response(status=404)

        return Response(_serialize_event_detail(event))


class AgentVulnerabilitiesView(APIView):
    def get(self, request, agent_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        err = _resolve_agent(request, org, agent_id)
        if err:
            return err

        severity_raw = request.query_params.get("severity", "").strip()
        severity = [s.strip() for s in severity_raw.split(",") if s.strip()] or None
        fix_available_raw = request.query_params.get("fix_available", "").strip().lower()
        fix_available = True if fix_available_raw == "true" else None
        search = request.query_params.get("search", "").strip()
        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 50))
        except ValueError:
            return Response({"detail": "offset and limit must be integers."}, status=400)

        is_first_page = offset == 0 and limit == 50
        cache_key = _vulns_cache_key(agent_id, org.slug, severity=severity, fix_available=fix_available, search=search)

        if is_first_page:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            result = OpenSearchClient().get_agent_vulnerabilities(
                agent_id, offset=offset, limit=limit,
                severity=severity, fix_available=fix_available, search=search,
            )
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in AgentVulnerabilitiesView")
            return Response({"detail": "Search service unavailable."}, status=502)

        cached_agents = cache.get(_agents_cache_key(org.slug)) or []
        agent_raw = next((a for a in cached_agents if str(a.get("id")) == str(agent_id)), {})
        os_info = agent_raw.get("os", {})
        raw_platform = os_info.get("platform", "") if isinstance(os_info, dict) else ""
        agent_platform = normalize_platform(raw_platform)

        serialized = [_serialize_vulnerability(v) for v in result["vulnerabilities"]]
        serialized.sort(key=lambda v: _SEVERITY_ORDER.get(v["severity"], 99))

        if agent_platform:
            for vuln in serialized:
                adv = get_or_fetch_advisory(vuln["cve"], agent_platform)
                vuln["advisory"] = {
                    "platform": agent_platform,
                    "advisory_url": adv.advisory_url,
                    "remediation_text": adv.remediation_text,
                }
        else:
            for vuln in serialized:
                vuln["advisory"] = None

        data = PaginatedVulnerabilitiesSerializer({
            "vulnerabilities": serialized,
            "total": result["total"],
        }).data

        if is_first_page:
            cache.set(cache_key, data, _VULNS_CACHE_TTL)

        return Response(data)


class AgentVulnerabilityDetailView(APIView):
    def get(self, request, agent_id, vuln_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        err = _resolve_agent(request, org, agent_id)
        if err:
            return err

        try:
            vuln = OpenSearchClient().get_vulnerability_by_id(agent_id, vuln_id)
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in AgentVulnerabilityDetailView")
            return Response({"detail": "Search service unavailable."}, status=502)

        if vuln is None:
            return Response(status=404)

        return Response(_serialize_vulnerability_detail(vuln))


_FLEET_VULNS_CACHE_TTL = 300  # 5 min — fleet-wide CVE aggregation
_VALID_SORT_FIELDS = {"severity", "cvss_score", "affected_agents", "published"}


def _fleet_vulns_cache_key(org_slug, severity=None, fix_available=None, search="", agent_id="", sort_by="severity", sort_order="desc"):
    sev_part = ",".join(sorted(severity)) if severity else ""
    fix_part = "1" if fix_available else ""
    return f"fleet_vulns_{org_slug}_{sev_part}_{fix_part}_{search}_{agent_id}_{sort_by}_{sort_order}"


class FleetVulnerabilitiesView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        severity_raw = request.query_params.get("severity", "").strip()
        severity = [s.strip() for s in severity_raw.split(",") if s.strip()] or None
        fix_available_raw = request.query_params.get("fix_available", "").strip().lower()
        fix_available = True if fix_available_raw == "true" else None
        search = request.query_params.get("search", "").strip()
        agent_id_filter = request.query_params.get("agent", "").strip() or None
        sort_by = request.query_params.get("sort_by", "severity").strip()
        sort_order = request.query_params.get("sort_order", "desc").strip()
        if sort_by not in _VALID_SORT_FIELDS:
            sort_by = "severity"
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"
        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 50))
        except ValueError:
            return Response({"detail": "offset and limit must be integers."}, status=400)

        cache_key = _fleet_vulns_cache_key(
            org.slug, severity=severity, fix_available=fix_available,
            search=search, agent_id=agent_id_filter or "",
            sort_by=sort_by, sort_order=sort_order,
        )
        is_first_page = offset == 0 and limit == 50
        if is_first_page:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("Wazuh error in FleetVulnerabilitiesView")
            return Response({"detail": "Security service unavailable."}, status=502)

        agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]

        try:
            result = OpenSearchClient().get_fleet_vulnerabilities(
                agent_ids,
                severity=severity,
                fix_available=fix_available,
                search=search,
                agent_id_filter=agent_id_filter,
                offset=offset,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in FleetVulnerabilitiesView")
            return Response({"detail": "Search service unavailable."}, status=502)

        fleet_platforms = {
            normalize_platform(a.get("os", {}).get("platform", "") if isinstance(a.get("os"), dict) else "")
            for a in raw_agents
            if a.get("status") == "active"
        }
        fleet_platforms.discard("")

        for vuln in result["vulnerabilities"]:
            vuln["advisories"] = [
                {
                    "platform": platform,
                    "advisory_url": adv.advisory_url,
                    "remediation_text": adv.remediation_text,
                }
                for platform in sorted(fleet_platforms)
                for adv in [get_or_fetch_advisory(vuln["cve"], platform)]
            ]

        data = FleetVulnerabilitiesResponseSerializer(result).data
        if is_first_page:
            cache.set(cache_key, data, _FLEET_VULNS_CACHE_TTL)
        return Response(data)


class FleetVulnerabilityTrendView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            return Response({"detail": "days must be an integer."}, status=400)
        if days not in (7, 30, 90):
            days = 30

        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=days)
        snapshots = (
            VulnerabilitySnapshot.objects
            .filter(organization=org, date__gte=cutoff)
            .order_by("date")
        )
        data = VulnerabilitySnapshotSerializer(snapshots, many=True).data
        return Response({"snapshots": data})


_FLEET_EVENTS_CACHE_TTL = 60   # 1 minute — fleet events change frequently
_VALID_MINUTES = {5, 15, 30, 60, 360, 1440, 10080, 43200}


class FleetEventsView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        try:
            minutes = int(request.query_params.get("minutes", 1440))
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            return Response({"detail": "minutes, offset and limit must be integers."}, status=400)

        if minutes not in _VALID_MINUTES:
            return Response(
                {"detail": f"minutes must be one of {sorted(_VALID_MINUTES)}."},
                status=400,
            )

        severity_raw = request.query_params.get("severity", "").strip()
        severity = [s.strip() for s in severity_raw.split(",") if s.strip()] or None
        search = request.query_params.get("search", "").strip()
        agent_filter = request.query_params.get("agent", "").strip()

        # Resolve agent filter — non-staff users restricted to their org's agents
        if agent_filter:
            err = _resolve_agent(request, org, agent_filter)
            if err:
                return err

        cached_agents = cache.get(_agents_cache_key(org.slug))
        if cached_agents is None:
            return Response({"detail": "Agent list not available. Try refreshing."}, status=503)
        agent_ids = [str(a["id"]) for a in cached_agents]

        cache_key = _fleet_events_cache_key(
            org.slug, minutes=minutes, severity=severity,
            search=search, agent_filter=agent_filter, offset=offset,
        )
        if offset == 0:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            result = OpenSearchClient().get_fleet_events(
                agent_ids,
                minutes=minutes,
                offset=offset,
                limit=limit,
                severity=severity,
                search=search,
                agent_id_filter=agent_filter or None,
            )
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in FleetEventsView")
            return Response({"detail": "Search service unavailable."}, status=502)

        data = {
            "events": [_serialize_event(e) for e in result["events"]],
            "total": result["total"],
            "stats": result["stats"],
        }

        if offset == 0:
            cache.set(cache_key, data, _FLEET_EVENTS_CACHE_TTL)

        return Response(data)


class CveDetailView(APIView):
    def get(self, request, cve_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("Wazuh error in CveDetailView")
            return Response({"detail": "Security service unavailable."}, status=502)

        agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]
        agent_map = {str(a["id"]): _serialize_agent(a) for a in raw_agents}

        try:
            os_client = OpenSearchClient()
            sample = os_client.get_cve_detail(agent_ids, cve_id)
            if sample is None:
                return Response(status=404)
            affected_docs = os_client.get_cve_affected_agents(agent_ids, cve_id)
        except OpenSearchError as exc:
            logger.exception("OpenSearch error in CveDetailView")
            return Response({"detail": "Search service unavailable."}, status=502)

        v = sample.get("vulnerability", {})
        pkg = sample.get("package", {})
        cvss = v.get("cvss", {}).get("cvss3", {})
        refs = v.get("references", [])

        affected = []
        for doc in affected_docs:
            a = doc.get("agent", {})
            p = doc.get("package", {})
            dv = doc.get("vulnerability", {})
            agent_info = agent_map.get(str(a.get("id", "")), {})
            affected.append({
                "agent_id": str(a.get("id", "")),
                "agent_name": a.get("name") or agent_info.get("name") or "",
                "installed_version": p.get("version") or None,
                "fixed_version": p.get("fixed_version") or None,
                "fix_available": dv.get("status", "").lower() == "fixed",
            })

        platforms = {
            normalize_platform(agent_map.get(a["agent_id"], {}).get("os_platform", ""))
            for a in affected
        }
        platforms.discard("")

        advisories = [
            {
                "platform": platform,
                "advisory_url": adv.advisory_url,
                "remediation_text": adv.remediation_text,
            }
            for platform in sorted(platforms)
            for adv in [get_or_fetch_advisory(cve_id, platform)]
        ]

        detail = {
            "cve": v.get("id", cve_id),
            "severity": v.get("severity", "").lower(),
            "cvss_score": cvss.get("base_score"),
            "package": pkg.get("name", ""),
            "description": v.get("description", ""),
            "published": v.get("published") or None,
            "affected_agents": affected,
            "advisories": advisories,
        }
        if refs:
            detail["references"] = refs if isinstance(refs, list) else [refs]

        return Response(CveDetailSerializer(detail).data)


class EnrollmentView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        manager_host = os.environ.get("WAZUH_MANAGER_HOST", "")
        agent_version = os.environ.get("WAZUH_AGENT_VERSION", "4.12.0-1")
        registration_password = os.environ.get("WAZUH_REGISTRATION_PASSWORD", "")
        linux_parts = [
            f"WAZUH_MANAGER='{manager_host}'",
            f"WAZUH_AGENT_GROUP='{org.wazuh_group}'",
        ]
        if registration_password:
            linux_parts.append(f"WAZUH_REGISTRATION_PASSWORD='{registration_password}'")
        install_command = (
            " ".join(linux_parts)
            + " apt-get install -y wazuh-agent && "
            "systemctl daemon-reload && "
            "systemctl enable --now wazuh-agent"
        )
        windows_msiexec = (
            f"msiexec.exe /i $installer /q WAZUH_MANAGER='{manager_host}' WAZUH_AGENT_GROUP='{org.wazuh_group}'"
        )
        if registration_password:
            windows_msiexec += f" WAZUH_REGISTRATION_PASSWORD='{registration_password}'"
        windows_install_command = (
            f"$installer = \"$env:tmp\\wazuh-agent.msi\"\n"
            f"Invoke-WebRequest -Uri 'https://packages.wazuh.com/4.x/windows/wazuh-agent-{agent_version}.msi' "
            f"-OutFile $installer\n"
            f"{windows_msiexec}\n"
            f"NET START WazuhSvc"
        )
        data = EnrollmentSerializer({
            "wazuh_group": org.wazuh_group,
            "manager_host": manager_host,
            "install_command": install_command,
            "windows_install_command": windows_install_command,
        }).data
        return Response(data)


class DownloadListView(APIView):
    def get(self, request):
        org_slug = request.query_params.get("org", "").strip()

        if org_slug:
            org, err = _resolve_org(request, org_slug)
            if err:
                return err
            downloads = Download.objects.filter(
                Q(organization=None) | Q(organization=org)
            ).select_related("organization")
        else:
            if not request.user.is_staff:
                return Response({"detail": "org is required."}, status=400)
            downloads = Download.objects.all().select_related("organization")

        return Response(DownloadSerializer(downloads, many=True).data)

    def post(self, request):
        if not request.user.is_staff:
            return Response(status=403)

        serializer = DownloadCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        org = None
        org_slug = data.get("organization_slug", "").strip()
        if org_slug:
            try:
                org = Organization.objects.get(slug=org_slug)
            except Organization.DoesNotExist:
                return Response({"detail": "Organization not found."}, status=404)

        download = Download.objects.create(
            label=data["label"],
            platform=data["platform"],
            category=data["category"],
            organization=org,
        )
        return Response(DownloadSerializer(download).data, status=201)


class DownloadDeleteView(APIView):
    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(status=403)
        try:
            download = Download.objects.get(pk=pk)
        except Download.DoesNotExist:
            return Response(status=404)
        if download.s3_key:
            StorageClient().delete_file(download.s3_key)
        download.delete()
        return Response(status=204)


class DownloadPresignedView(APIView):
    def get(self, request, pk):
        try:
            download = Download.objects.select_related("organization").get(pk=pk)
        except Download.DoesNotExist:
            return Response(status=404)

        if download.organization is not None:
            if not request.user.is_staff:
                if not OrganizationMembership.objects.filter(
                    user=request.user, organization=download.organization
                ).exists():
                    return Response(status=403)

        if not download.s3_key:
            return Response({"detail": "No file uploaded yet."}, status=404)

        url = StorageClient().generate_presigned_url(download.s3_key, expiry_seconds=300)
        return Response({"url": url})


class DownloadUploadView(APIView):
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response(status=403)

        try:
            download = Download.objects.get(pk=pk)
        except Download.DoesNotExist:
            return Response(status=404)

        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "file is required."}, status=400)

        key = f"downloads/{download.pk}/{file.name}"
        StorageClient().upload_file(file, key)
        download.s3_key = key
        download.save()

        return Response(DownloadSerializer(download).data)


def _enrich_work_package_with_advisories(package, org_slug):
    """Attach advisories to each WorkPackageItem using platforms from the cached agent list."""
    cached_agents = cache.get(_agents_cache_key(org_slug)) or []
    agent_platform_map = {}
    for a in cached_agents:
        os_info = a.get("os", {})
        raw_platform = os_info.get("platform", "") if isinstance(os_info, dict) else ""
        platform = normalize_platform(raw_platform)
        if platform:
            agent_platform_map[str(a.get("id", ""))] = platform

    for item in package.items.all():
        platforms = {
            agent_platform_map[str(a.get("agent_id", ""))]
            for a in (item.affected_agents or [])
            if str(a.get("agent_id", "")) in agent_platform_map
        }
        if not platforms and agent_platform_map:
            platforms = set(agent_platform_map.values())

        item._advisories = [
            {
                "platform": platform,
                "advisory_url": adv.advisory_url,
                "remediation_text": adv.remediation_text,
            }
            for platform in sorted(platforms)
            for adv in [get_or_fetch_advisory(item.cve_id, platform)]
        ]


class WorkPackageView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        package = (
            WorkPackage.objects
            .filter(org=org, status=WorkPackage.STATUS_ACTIVE)
            .prefetch_related("items")
            .first()
        )
        if package is None:
            return Response({"package": None})

        _enrich_work_package_with_advisories(package, org.slug)

        serialized = WorkPackageSerializer(package)
        return Response({"package": serialized.data})


class WorkPackageGenerateView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response(status=403)

        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        package = generate_work_package(org, generated_by=request.user)

        if package is None:
            return Response(
                {"detail": "No CVE data available for this organisation."},
                status=502,
            )

        package = WorkPackage.objects.prefetch_related("items").get(pk=package.pk)
        return Response({"package": WorkPackageSerializer(package).data}, status=201)


class WorkPackageItemPatchView(APIView):
    def patch(self, request, item_id):
        try:
            item = WorkPackageItem.objects.select_related("work_package__org").get(pk=item_id)
        except WorkPackageItem.DoesNotExist:
            return Response(status=404)

        org = item.work_package.org
        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
                return Response(status=403)

        if item.work_package.status != WorkPackage.STATUS_ACTIVE:
            return Response({"detail": "Cannot update items on an archived work package."}, status=400)

        serializer = WorkPackageItemUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "")
        if new_status != WorkPackageItem.STATUS_ACCEPTED_RISK:
            note = ""

        prev_status = item.status

        with transaction.atomic():
            if new_status == WorkPackageItem.STATUS_ACCEPTED_RISK:
                RiskAcceptance.objects.update_or_create(
                    org=org,
                    cve_id=item.cve_id,
                    defaults={
                        "accepted_by": request.user,
                        "note": note,
                        "severity": item.severity,
                        "cvss_score": item.cvss_score,
                    },
                )
                item.status = new_status
                item.note = note
                item.save(update_fields=["status", "note"])
            elif prev_status == WorkPackageItem.STATUS_ACCEPTED_RISK:
                RiskAcceptance.objects.filter(org=org, cve_id=item.cve_id).delete()
                WorkPackageItem.objects.filter(
                    work_package__org=org,
                    cve_id=item.cve_id,
                ).update(status=WorkPackageItem.STATUS_OPEN, note="")
                item.refresh_from_db()
            else:
                item.status = new_status
                item.note = note
                item.save(update_fields=["status", "note"])

        return Response(WorkPackageItemSerializer(item).data)

    def delete(self, request, item_id):
        if not request.user.is_staff:
            return Response(status=403)

        try:
            item = WorkPackageItem.objects.select_related("work_package").get(pk=item_id)
        except WorkPackageItem.DoesNotExist:
            return Response(status=404)

        if item.work_package.status != WorkPackage.STATUS_ACTIVE:
            return Response({"detail": "Cannot remove items from an archived work package."}, status=400)

        item.delete()
        return Response(status=204)


class WorkPackageAddMoreView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response(status=403)

        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        package = (
            WorkPackage.objects
            .prefetch_related("items")
            .filter(org=org, status=WorkPackage.STATUS_ACTIVE)
            .first()
        )
        if package is None:
            return Response({"detail": "No active work package for this organisation."}, status=404)

        new_items, exhausted = add_more_items(package)
        return Response({
            "items": WorkPackageItemSerializer(new_items, many=True).data,
            "exhausted": exhausted,
        })


class WorkPackageArchiveListView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        packages = (
            WorkPackage.objects
            .filter(org=org, status=WorkPackage.STATUS_ARCHIVED)
            .annotate(item_count=Count("items"))
            .order_by("-created_at")
        )
        return Response(WorkPackageArchiveListSerializer(packages, many=True).data)


class WorkPackageDetailView(APIView):
    def get(self, request, package_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        try:
            package = (
                WorkPackage.objects
                .prefetch_related("items")
                .get(pk=package_id, org=org)
            )
        except WorkPackage.DoesNotExist:
            return Response(status=404)

        _enrich_work_package_with_advisories(package, org.slug)
        return Response({"package": WorkPackageSerializer(package).data})


class AgentRespondView(APIView):
    """POST /api/security/agents/<agent_id>/respond/ — fire a Wazuh active response against a host."""

    def post(self, request, agent_id):
        import logging as _logging
        _log = _logging.getLogger(__name__)

        if not request.user.is_staff:
            return Response(status=403)

        slug = request.data.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        from automations.models import WazuhActiveResponse
        from automations.interpolation import interpolate_args
        from incidents.models import Comment, Incident, IncidentEvent, WazuhResponseExecution
        from incidents.services.events import record_event

        response_id = request.data.get("wazuh_response")
        if not response_id:
            return Response({"detail": "wazuh_response is required."}, status=400)

        try:
            wr = WazuhActiveResponse.objects.get(pk=response_id, archived=False)
        except WazuhActiveResponse.DoesNotExist:
            return Response({"detail": "Wazuh response not found."}, status=404)

        if not wr.available_in_security_overview:
            return Response({"detail": "This response is not available in the security overview."}, status=400)

        # Fetch agent to validate OS compatibility
        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError):
            return Response({"detail": "Security service unavailable."}, status=502)

        agent_raw = next((a for a in raw_agents if str(a.get("id")) == str(agent_id)), None)
        if agent_raw is None:
            return Response(status=404)

        os_info = agent_raw.get("os", {})
        _raw_platform = os_info.get("platform", "").lower() if isinstance(os_info, dict) else ""
        _LINUX_DISTROS = {
            "ubuntu", "debian", "raspbian", "centos", "rhel", "fedora",
            "arch", "alpine", "amzn", "sles", "opensuse", "manjaro", "mint",
            "kali", "parrot", "oracle",
        }
        if _raw_platform in _LINUX_DISTROS:
            agent_platform = "linux"
        elif _raw_platform == "darwin":
            agent_platform = "macos"
        else:
            agent_platform = _raw_platform

        if wr.platforms and agent_platform and agent_platform not in wr.platforms:
            return Response(
                {"detail": f"Agent OS '{agent_platform}' is not in this response's platforms: {wr.platforms}."},
                status=400,
            )

        # Resolve args
        override_args = (request.data.get("args") or "").strip()
        incident_id = request.data.get("incident")
        incident = None

        if incident_id:
            try:
                incident = Incident.objects.prefetch_related("assets", "iocs").get(display_id=incident_id)
            except Incident.DoesNotExist:
                return Response({"detail": "Incident not found."}, status=404)
            resolved_args = override_args if override_args else interpolate_args(wr.default_args, incident)
        else:
            resolved_args = override_args if override_args else wr.default_args

        timeout_val = request.data.get("timeout")
        timeout = int(timeout_val) if timeout_val is not None else wr.timeout

        wazuh_status_code = None
        wazuh_response_body = {}
        error_msg = None

        try:
            client = WazuhClient()
            wazuh_status_code, wazuh_response_body = client.run_active_response(
                command=wr.command,
                agent_ids=[str(agent_id)],
                args=resolved_args,
                timeout=timeout,
            )
        except (WazuhAuthError, WazuhAPIError) as exc:
            _log.exception("WazuhAPIError in AgentRespondView for agent_id=%s", agent_id)
            error_msg = "Wazuh service error."

        from django.db import transaction
        with transaction.atomic():
            task = None
            if incident:
                from incidents.models import Task
                task = Task.objects.create(
                    incident=incident,
                    title=f"Wazuh response: {wr.name}",
                    task_type=Task.TYPE_WAZUH_RESPONSE,
                    wazuh_response=wr,
                    state=Task.STATE_DONE,
                    assignee=request.user,
                    automation_error=error_msg,
                )

            execution = WazuhResponseExecution.objects.create(
                wazuh_response=wr,
                executed_by=request.user,
                agent_ids=[str(agent_id)],
                resolved_args=resolved_args,
                timeout_used=timeout,
                incident=incident,
                task=task,
                wazuh_status_code=wazuh_status_code,
                wazuh_response_body=wazuh_response_body,
            )

            if incident:
                if error_msg:
                    body = (
                        f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to agent `{agent_id}` "
                        f"from security overview by {request.user.username}. **Error:** {error_msg}"
                    )
                else:
                    body = (
                        f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to agent `{agent_id}` "
                        f"from security overview by {request.user.username}. Status {wazuh_status_code}."
                    )
                Comment.objects.create(
                    incident=incident,
                    author=request.user,
                    body=body,
                    kind=Comment.KIND_SYSTEM,
                )
                record_event(
                    incident,
                    "wazuh_response_dispatched",
                    actor=request.user,
                    payload={
                        "agent_id": str(agent_id),
                        "wazuh_response_id": wr.id,
                        "wazuh_response_name": wr.name,
                        "execution_id": execution.id,
                        "status_code": wazuh_status_code,
                        "error": error_msg,
                    },
                )

        return Response({
            "id": execution.id,
            "wazuh_response": wr.id,
            "wazuh_response_name": wr.name,
            "agent_id": str(agent_id),
            "resolved_args": resolved_args,
            "timeout_used": timeout,
            "wazuh_status_code": wazuh_status_code,
            "error": error_msg,
            "incident": incident.display_id if incident else None,
            "task_id": task.id if task else None,
        }, status=201)


class AgentResponseHistoryView(APIView):
    """GET /api/security/agents/<agent_id>/responses/ — list WazuhResponseExecution records."""

    def get(self, request, agent_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        err = _resolve_agent(request, org, agent_id)
        if err:
            return err

        from incidents.models import WazuhResponseExecution
        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 50))
        except ValueError:
            return Response({"detail": "offset and limit must be integers."}, status=400)

        qs = (
            WazuhResponseExecution.objects
            .filter(agent_ids__icontains=f'"{agent_id}"')
            .select_related("wazuh_response", "executed_by", "incident", "task")
            .order_by("-executed_at")
        )
        total = qs.count()
        executions = qs[offset:offset + limit]

        data = []
        for ex in executions:
            data.append({
                "id": ex.id,
                "executed_at": ex.executed_at.isoformat(),
                "response_name": ex.wazuh_response.name,
                "command": ex.wazuh_response.command,
                "executed_by": ex.executed_by.username if ex.executed_by else None,
                "resolved_args": ex.resolved_args,
                "timeout_used": ex.timeout_used,
                "incident_display_id": ex.incident.display_id if ex.incident else None,
                "incident_title": ex.incident.title if ex.incident else None,
                "wazuh_status_code": ex.wazuh_status_code,
            })

        return Response({"executions": data, "total": total})


class RiskAcceptanceListView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        acceptances = RiskAcceptance.objects.filter(org=org).select_related("accepted_by").order_by("-accepted_at")
        return Response(RiskAcceptanceSerializer(acceptances, many=True).data)


class RiskAcceptanceDeleteView(APIView):
    def delete(self, request, pk):
        try:
            ra = RiskAcceptance.objects.select_related("org").get(pk=pk)
        except RiskAcceptance.DoesNotExist:
            return Response(status=404)

        org = ra.org
        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
                return Response(status=403)

        with transaction.atomic():
            cve_id = ra.cve_id
            ra.delete()
            WorkPackageItem.objects.filter(
                work_package__org=org,
                cve_id=cve_id,
            ).update(status=WorkPackageItem.STATUS_OPEN, note="")

        return Response(status=204)
