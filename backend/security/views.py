import os

from django.core.cache import cache
from django.db import transaction
from django.utils.text import slugify
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count, Q
from security.models import Download, Organization, OrganizationMembership, VulnerabilitySnapshot, WorkPackage, WorkPackageItem
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
    VulnerabilitySnapshotSerializer,
    WorkPackageArchiveListSerializer,
    WorkPackageItemSerializer,
    WorkPackageItemUpdateSerializer,
    WorkPackageSerializer,
)
from security.storage import StorageClient
from security.work_package_service import generate_work_package
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
    else:
        os_label = ""
    return {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "ip": agent.get("ip"),
        "status": agent.get("status"),
        "os": os_label,
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
            return Response({"detail": str(exc)}, status=502)
        agent_ids = {str(a.get("id")) for a in raw_agents}
    if str(agent_id) not in agent_ids:
        return Response(status=403)
    return None


class OrganizationListView(APIView):
    def get(self, request):
        if request.user.is_staff:
            orgs = Organization.objects.all().order_by("name")
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
            return Response({"detail": f"Failed to create Wazuh group: {exc}"}, status=400)

        return Response(OrganizationSerializer(org).data, status=201)


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
            return Response({"detail": str(exc)}, status=502)

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
            os_client = OpenSearchClient()
            vuln_summary = os_client.get_vulnerabilities_summary(raw_agents)
            event_count = os_client.get_events_count(raw_agents)
        except (WazuhAuthError, WazuhAPIError, OpenSearchError) as exc:
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

        serialized = [_serialize_vulnerability(v) for v in result["vulnerabilities"]]
        serialized.sort(key=lambda v: _SEVERITY_ORDER.get(v["severity"], 99))

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

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
            return Response({"detail": str(exc)}, status=502)

        agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]
        agent_map = {str(a["id"]): _serialize_agent(a) for a in raw_agents}

        try:
            os_client = OpenSearchClient()
            sample = os_client.get_cve_detail(agent_ids, cve_id)
            if sample is None:
                return Response(status=404)
            affected_docs = os_client.get_cve_affected_agents(agent_ids, cve_id)
        except OpenSearchError as exc:
            return Response({"detail": str(exc)}, status=502)

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

        detail = {
            "cve": v.get("id", cve_id),
            "severity": v.get("severity", "").lower(),
            "cvss_score": cvss.get("base_score"),
            "package": pkg.get("name", ""),
            "description": v.get("description", ""),
            "published": v.get("published") or None,
            "affected_agents": affected,
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
        install_command = (
            f"WAZUH_MANAGER='{manager_host}' "
            f"WAZUH_AGENT_GROUP='{org.wazuh_group}' "
            f"apt-get install -y wazuh-agent && "
            f"systemctl daemon-reload && "
            f"systemctl enable --now wazuh-agent"
        )
        data = EnrollmentSerializer({
            "wazuh_group": org.wazuh_group,
            "manager_host": manager_host,
            "install_command": install_command,
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
        return Response({"package": WorkPackageSerializer(package).data})


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

        item.status = new_status
        item.note = note
        item.save(update_fields=["status", "note"])

        return Response(WorkPackageItemSerializer(item).data)


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

        return Response({"package": WorkPackageSerializer(package).data})
