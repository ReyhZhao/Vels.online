import os

from django.core.cache import cache
from django.db import transaction
from django.utils.text import slugify
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q
from security.models import Download, Organization, OrganizationMembership
from security.serializers import (
    AgentSerializer,
    DownloadCreateSerializer,
    DownloadSerializer,
    EnrollmentSerializer,
    OrganizationSerializer,
    PaginatedEventsSerializer,
    PaginatedVulnerabilitiesSerializer,
)
from security.storage import StorageClient
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


def _events_cache_key(agent_id, org_slug):
    return f"security_events_{agent_id}_{org_slug}"


def _vulns_cache_key(agent_id, org_slug):
    return f"security_vulns_{agent_id}_{org_slug}"


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
        "timestamp": event.get("@timestamp") or event.get("timestamp"),
        "rule_description": rule.get("description", ""),
        "rule_id": rule.get("id", ""),
        "level": level,
        "severity": _event_severity(level),
        "agent_name": agent.get("name", ""),
    }


def _serialize_vulnerability(vuln):
    v = vuln.get("vulnerability", {})
    pkg = vuln.get("package", {})
    return {
        "cve": v.get("id", ""),
        "package": pkg.get("name", ""),
        "version": pkg.get("version", ""),
        "severity": v.get("severity", "").lower(),
        "fix_available": v.get("status", "").lower() == "fixed",
    }


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

        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            return Response({"detail": "offset and limit must be integers."}, status=400)

        is_first_page = offset == 0 and limit == 100
        cache_key = _events_cache_key(agent_id, org.slug)

        if is_first_page:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            result = OpenSearchClient().get_agent_events(agent_id, hours=24, offset=offset, limit=limit)
        except OpenSearchError as exc:
            return Response({"detail": str(exc)}, status=502)

        data = PaginatedEventsSerializer({
            "events": [_serialize_event(e) for e in result["events"]],
            "total": result["total"],
        }).data

        if is_first_page:
            cache.set(cache_key, data, _EVENTS_CACHE_TTL)

        return Response(data)


class AgentVulnerabilitiesView(APIView):
    def get(self, request, agent_id):
        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 50))
        except ValueError:
            return Response({"detail": "offset and limit must be integers."}, status=400)

        is_first_page = offset == 0 and limit == 50
        cache_key = _vulns_cache_key(agent_id, org.slug)

        if is_first_page:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)

        try:
            result = OpenSearchClient().get_agent_vulnerabilities(agent_id, offset=offset, limit=limit)
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
