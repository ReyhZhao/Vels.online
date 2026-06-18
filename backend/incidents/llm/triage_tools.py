"""Tools for the unattended Triage Agent's Work phase (ADR-0024).

Unlike the Incident Assistant's tools — which bind to a *user* and scope reads via
that user's authorization — the Triage Agent runs with no human present, so its read
tools are scoped directly to the bound incident's **organization** (the tenant-isolation
invariant). It never widens cross-org.

Slice 4 is read-only: app lookups + IT Hygiene inventory + PAP-gated web search. The
executed *write* tools (apply_task_template, run_task, add_task_comment, ...) are added
in later slices and listed in the triage action-authority module.
"""
from assistants.tools import ToolResult, ToolSpec
from assistants.web_search import build_web_search_tool, web_search_available
from assistants import pap_guard

# Reuse the assistant's host-inventory tool: it scopes purely by the incident's
# organisation (never by user), so it is already correct for the unattended agent.
from incidents.llm.assistant_tools import _host_inventory

_LIMIT = 10


def _lookup_incidents(incident):
    def executor(args):
        from incidents.models import Incident
        from django.db.models import Q
        q = ((args or {}).get("query") or "").strip()
        qs = Incident.objects.filter(organization=incident.organization).exclude(pk=incident.pk)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        rows = list(qs.order_by("-created_at").values(
            "display_id", "title", "severity", "state", "created_at")[:_LIMIT])
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} related incidents", count=len(rows))
    return ToolSpec(
        name="lookup_incidents",
        description="Search other incidents in THIS incident's organisation (related campaigns, "
                    "the same indicator elsewhere).",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in title/description."}}},
        executor=executor,
    )


def _query_alerts(incident):
    def executor(args):
        from alerts.models import Alert
        q = ((args or {}).get("query") or "").strip()
        qs = Alert.objects.filter(organization=incident.organization)
        if q:
            qs = qs.filter(title__icontains=q)
        rows = list(qs.order_by("-created_at").values(
            "display_id", "title", "severity", "state", "source_kind", "created_at")[:_LIMIT])
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} alerts", count=len(rows))
    return ToolSpec(
        name="query_alerts",
        description="Search alerts in THIS incident's organisation (does the same indicator appear "
                    "elsewhere?).",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in the alert title."}}},
        executor=executor,
    )


def _lookup_assets(incident):
    def executor(args):
        from incidents.models import Asset
        from django.db.models import Q
        q = ((args or {}).get("query") or "").strip()
        qs = Asset.objects.filter(organization=incident.organization)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(agent_name__icontains=q) | Q(ip_address__icontains=q))
        rows = list(qs.values("id", "name", "kind", "agent_name", "ip_address", "role")[:_LIMIT])
        for r in rows:
            r["ip_address"] = str(r["ip_address"]) if r["ip_address"] else None
        return ToolResult(content=rows, summary=f"{len(rows)} assets", count=len(rows))
    return ToolSpec(
        name="lookup_assets",
        description="Look up assets (hosts) in THIS incident's organisation to understand exposure "
                    "and ownership.",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "Text to match in name/agent_name/ip."}}},
        executor=executor,
    )


def build_triage_read_tools(incident, grounding, *, include_web_search=True,
                            os_client=None, wazuh_client=None):
    """Read-only tool set for the Triage Agent, scoped to the incident's org.

    `include_web_search` should be False when the provider has native web search.
    Web search obeys the incident's PAP exactly as the assistant's does (ADR-0011).
    """
    tools = [
        _lookup_incidents(incident),
        _query_alerts(incident),
        _lookup_assets(incident),
        _host_inventory(incident, None, os_client=os_client, wazuh_client=wazuh_client),
    ]

    if include_web_search and web_search_available():
        indicators = pap_guard.collect_incident_indicators(grounding)
        pap_level = (grounding.get("incident", {}) or {}).get("pap", "")

        def guard(query):
            return pap_guard.check_web_search_query(query, indicators, pap_level)

        tools.append(build_web_search_tool(guard=guard))

    return tools
