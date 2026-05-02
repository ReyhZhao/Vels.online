import os

from django.core.cache import cache
from django.db import transaction
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.response import Response

from security.models import Organization, OrganizationMembership
from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

_CACHE_TTL = 60  # seconds


def _generate_slug(name):
    base = slugify(name)
    slug = base
    n = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _serialize_org(org):
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "wazuh_group": org.wazuh_group,
    }


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


def _dashboard_cache_key(slug):
    return f"security_dashboard_{slug}"


def _agents_cache_key(slug):
    return f"security_agents_{slug}"


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


@api_view(["GET", "POST"])
def organizations_view(request):
    if request.method == "GET":
        if request.user.is_staff:
            orgs = Organization.objects.all().order_by("name")
        else:
            orgs = Organization.objects.filter(
                memberships__user=request.user
            ).order_by("name")
        return Response([_serialize_org(o) for o in orgs])

    # POST — admin only
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

    return Response(_serialize_org(org), status=201)


@api_view(["GET"])
def agents_view(request):
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

    data = [_serialize_agent(a) for a in raw_agents]
    cache.set(cache_key, data, _CACHE_TTL)
    return Response(data)


@api_view(["GET"])
def dashboard_view(request):
    slug = request.query_params.get("org", "").strip()
    org, err = _resolve_org(request, slug)
    if err:
        return err

    cache_key = _dashboard_cache_key(org.slug)
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    client = WazuhClient()
    try:
        raw_agents = client.get_agents(org.wazuh_group)
        vuln_summary = client.get_vulnerabilities_summary(raw_agents)
        event_count = client.get_events_count(raw_agents)
    except (WazuhAuthError, WazuhAPIError) as exc:
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


@api_view(["POST"])
def refresh_view(request):
    slug = request.data.get("org", "").strip()
    org, err = _resolve_org(request, slug)
    if err:
        return err

    cache.delete(_dashboard_cache_key(org.slug))
    cache.delete(_agents_cache_key(org.slug))
    return Response({"detail": "Cache cleared."})


@api_view(["GET"])
def enrollment_view(request):
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
    return Response(
        {
            "wazuh_group": org.wazuh_group,
            "manager_host": manager_host,
            "install_command": install_command,
        }
    )
