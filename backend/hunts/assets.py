"""Render the in-scope asset inventory injected into a Hunt's LLM context (#512).

The model false-positives when it doesn't know which IPs / hostnames / domains belong
to the orgs in scope — it can flag the customer's *own* infrastructure as an attacker.
We already fetch each org's agent inventory (name / ip / os) in ``resolve_scope`` and
the org's public-facing assets live on ``ingress.Route``; this module folds both into a
compact, per-org, tenant-isolated context block that tells the model these are
known-good assets.

``build_asset_inventory`` is pure given the resolved scope and a routes map, so it is
unit-testable without Wazuh or the database. When ``routes_by_org`` is omitted it falls
back to querying ``Route`` for the in-scope (non-infrastructure) orgs.
"""
from typing import Dict, List, Optional

from .scope import OrgScope

# Bound the per-org agent list so a fleet of thousands can't blow the context window.
# The remainder is summarised as "… and N more agent(s)".
DEFAULT_MAX_AGENTS_PER_ORG = 40

_HEADER = (
    "IN-SCOPE ASSET INVENTORY — the assets below belong to the customer "
    "organisation(s) in scope for this hunt. Finding them in telemetry is expected. Do "
    "NOT, on their own, report these IPs, hostnames, or domains as indicators of "
    "compromise or attacker infrastructure; treat them as known-good when reasoning "
    "about who the attacker is."
)


def _fetch_routes_by_org(org_ids) -> Dict[int, list]:
    """Group each in-scope org's ingress routes (its own public assets) by org id."""
    from ingress.models import Route

    out: Dict[int, list] = {}
    if not org_ids:
        return out
    for r in Route.objects.filter(organization_id__in=list(org_ids)):
        out.setdefault(r.organization_id, []).append(r)
    return out


def _field(obj, key):
    """Read ``key`` from a Route model instance or a plain dict (test-friendly)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _format_org_section(scope: OrgScope, routes: list, max_agents: int) -> str:
    lines = [f"## {scope.org_name}"]
    if scope.is_infrastructure:
        lines.append(
            "Shared infrastructure (firewall / reverse proxy forwarded to the Wazuh "
            "manager, agent.id 000). No managed agents."
        )
    else:
        agents = scope.agents or []
        if agents:
            shown = agents[:max_agents]
            lines.append(f"Agents ({len(agents)}):")
            for a in shown:
                name = a.get("name") or a.get("id") or "?"
                ip = a.get("ip") or "?"
                osn = a.get("os") or "?"
                lines.append(f"- {name} — {ip} — {osn}")
            extra = len(agents) - len(shown)
            if extra > 0:
                lines.append(f"- … and {extra} more agent(s)")
        else:
            lines.append("Agents: none available.")
    if routes:
        lines.append(f"Ingress routes ({len(routes)}):")
        for r in routes:
            fqdn = _field(r, "fqdn") or "?"
            host = _field(r, "backend_host") or "?"
            port = _field(r, "backend_port")
            target = f"{host}:{port}" if port else host
            lines.append(f"- {fqdn} -> {target}")
    return "\n".join(lines)


def build_asset_inventory(
    scope: List[OrgScope],
    *,
    routes_by_org: Optional[Dict[int, list]] = None,
    max_agents_per_org: int = DEFAULT_MAX_AGENTS_PER_ORG,
) -> str:
    """Render the known-good asset inventory for the orgs in ``scope``.

    Each org gets its own section listing only that org's agents (name / ip / os) and
    ingress routes — tenant isolation is preserved because the inventory is built from
    the same per-org scope the lenses query. Returns "" for an empty scope.
    """
    if not scope:
        return ""
    if routes_by_org is None:
        real_ids = [s.org_id for s in scope if not s.is_infrastructure]
        routes_by_org = _fetch_routes_by_org(real_ids)
    sections = [
        _format_org_section(s, routes_by_org.get(s.org_id, []), max_agents_per_org)
        for s in scope
    ]
    return _HEADER + "\n\n" + "\n\n".join(sections)
