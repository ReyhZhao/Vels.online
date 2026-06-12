"""Hunt lens tools — the tenant-scoped query layer (ADR-0015, deep module).

A *lens* is a single-purpose, composable tool the model calls to query Wazuh telemetry.
Two families:

  - IOC sweep      — search for a specific indicator (hash / ip / domain / filename).
  - Behavioral     — open-ended exploration (top rules, histogram, top values,
                     agent activity, processes/ports).

Every lens iterates `ctx.scope` (one OrgScope per tenant) and issues **one query per
org**, scoped to that org's agent ids — so a cross-org hunt fans out per tenant and a
single query never joins across tenants. IOC sweeps and agent-activity record
HuntFindings (materialisable evidence); aggregations return summaries only.

The OpenSearch/Wazuh clients and the findings sink are injected through HuntContext so
the lenses are unit-testable without touching infrastructure.
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from assistants.tools import ToolResult, ToolSpec
from .scope import OrgScope

logger = logging.getLogger(__name__)

_ALERTS_INDEX = "wazuh-alerts-4.x-*"

# ECS-ish candidate fields per IOC type. A match on any counts.
_IOC_FIELDS = {
    "hash": [
        "data.win.eventdata.hashes", "syscheck.sha256_after", "syscheck.md5_after",
        "syscheck.sha1_after", "data.sha256", "data.md5",
    ],
    "ip": ["data.srcip", "data.dstip", "data.win.eventdata.destinationIp", "agent.ip"],
    "domain": [
        "data.dns.question.name", "data.url", "data.win.eventdata.queryName",
        "data.virustotal.permalink",
    ],
    "filename": [
        "data.win.eventdata.targetFilename", "data.win.eventdata.image",
        "syscheck.path", "data.file",
    ],
}

# Allowlisted fields the behavioral top_values lens may aggregate on. Keeping this
# tight bounds cost/abuse and keeps the schema reliable on the Ollama runtime.
_TOP_VALUE_FIELDS = [
    "rule.description", "rule.level", "rule.groups", "agent.name",
    "data.srcip", "data.dstip", "data.win.eventdata.image", "data.dstport",
]


@dataclass
class HuntContext:
    scope: List[OrgScope]
    lookback_days: int = 30
    os_client: object = None
    wazuh_client: object = None
    index: str = _ALERTS_INDEX
    max_findings_per_org: int = 50
    max_buckets: int = 20
    # record_findings(org_scope, lens_name, hits) -> None. Injected; writes HuntFinding.
    record_findings: Optional[Callable] = None


def _time_filter(days: int) -> dict:
    return {"range": {"@timestamp": {"gte": f"now-{int(days)}d"}}}


def _agents_filter(agent_ids: List[str]) -> dict:
    return {"terms": {"agent.id": [str(a) for a in agent_ids]}}


def _hits(data: dict) -> list:
    return (data or {}).get("hits", {}).get("hits", [])


# ── IOC sweep ─────────────────────────────────────────────────────────────────────

def _ioc_body(fields, value, agent_ids, days, size):
    return {
        "query": {"bool": {
            "filter": [_agents_filter(agent_ids), _time_filter(days)],
            "must": [{"bool": {
                "should": [{"match_phrase": {f: value}} for f in fields],
                "minimum_should_match": 1,
            }}],
        }},
        "sort": [{"@timestamp": {"order": "desc"}}],
        "size": size,
        "track_total_hits": True,
    }


def _ioc_search(ctx: HuntContext):
    def executor(args):
        ioc_type = (args or {}).get("ioc_type")
        value = ((args or {}).get("value") or "").strip()
        if ioc_type not in _IOC_FIELDS or not value:
            return ToolResult(
                error="ioc_type must be one of hash/ip/domain/filename and value is required",
                summary="bad args",
            )
        fields = _IOC_FIELDS[ioc_type]
        by_org, total = [], 0
        for s in ctx.scope:
            if not s.agent_ids:
                continue
            body = _ioc_body(fields, value, s.agent_ids, ctx.lookback_days, ctx.max_findings_per_org)
            data = ctx.os_client._search(ctx.index, body)
            hits = _hits(data)
            if hits:
                if ctx.record_findings:
                    ctx.record_findings(s, "ioc_search", hits)
                by_org.append({"organization": s.org_name, "count": len(hits)})
                total += len(hits)
        return ToolResult(
            content={"ioc_type": ioc_type, "value": value, "by_org": by_org, "total_matches": total},
            summary=f"{total} match(es) for {ioc_type} across {len(by_org)} org(s)",
            count=total,
        )

    return ToolSpec(
        name="ioc_search",
        description="Sweep the fleet for a specific indicator of compromise. Searches every "
                    "in-scope org's agents (fanned out per tenant) for the value across the "
                    "relevant Wazuh fields. Records matches as Findings.",
        parameters={"type": "object", "properties": {
            "ioc_type": {"type": "string", "enum": ["hash", "ip", "domain", "filename"]},
            "value": {"type": "string", "description": "The indicator value to search for."},
        }, "required": ["ioc_type", "value"]},
        executor=executor,
    )


# ── Behavioral lenses ───────────────────────────────────────────────────────────────

def _top_rules(ctx: HuntContext):
    def executor(args):
        by_org = []
        for s in ctx.scope:
            if not s.agent_ids:
                continue
            body = {
                "query": {"bool": {"filter": [_agents_filter(s.agent_ids), _time_filter(ctx.lookback_days)]}},
                "size": 0,
                "aggs": {"by_rule": {"terms": {"field": "rule.description", "size": ctx.max_buckets}}},
            }
            data = ctx.os_client._search(ctx.index, body)
            buckets = data.get("aggregations", {}).get("by_rule", {}).get("buckets", [])
            by_org.append({
                "organization": s.org_name,
                "top_rules": [{"rule": b["key"], "count": b["doc_count"]} for b in buckets],
            })
        return ToolResult(content={"by_org": by_org}, summary=f"top rules for {len(by_org)} org(s)")

    return ToolSpec(
        name="top_rules",
        description="Behavioral lens: the most frequent Wazuh rule descriptions per org over the "
                    "lookback window — a quick read of what is noisy/active in the fleet.",
        parameters={"type": "object", "properties": {}},
        executor=executor,
    )


def _event_histogram(ctx: HuntContext):
    def executor(args):
        interval = (args or {}).get("interval") or "1d"
        if interval not in ("1h", "6h", "1d"):
            interval = "1d"
        by_org = []
        for s in ctx.scope:
            if not s.agent_ids:
                continue
            body = {
                "query": {"bool": {"filter": [_agents_filter(s.agent_ids), _time_filter(ctx.lookback_days)]}},
                "size": 0,
                "aggs": {"over_time": {"date_histogram": {
                    "field": "@timestamp", "fixed_interval": interval,
                }}},
            }
            data = ctx.os_client._search(ctx.index, body)
            buckets = data.get("aggregations", {}).get("over_time", {}).get("buckets", [])
            by_org.append({
                "organization": s.org_name,
                "series": [{"t": b.get("key_as_string", b.get("key")), "count": b["doc_count"]} for b in buckets],
            })
        return ToolResult(content={"interval": interval, "by_org": by_org}, summary=f"histogram for {len(by_org)} org(s)")

    return ToolSpec(
        name="event_histogram",
        description="Behavioral lens: event volume over time per org (spot spikes/bursts). "
                    "interval is one of 1h/6h/1d.",
        parameters={"type": "object", "properties": {
            "interval": {"type": "string", "enum": ["1h", "6h", "1d"]},
        }},
        executor=executor,
    )


def _top_values(ctx: HuntContext):
    def executor(args):
        field_name = (args or {}).get("field")
        if field_name not in _TOP_VALUE_FIELDS:
            return ToolResult(
                error=f"field must be one of: {', '.join(_TOP_VALUE_FIELDS)}",
                summary="field not allowed",
            )
        by_org = []
        for s in ctx.scope:
            if not s.agent_ids:
                continue
            body = {
                "query": {"bool": {"filter": [_agents_filter(s.agent_ids), _time_filter(ctx.lookback_days)]}},
                "size": 0,
                "aggs": {"top": {"terms": {"field": field_name, "size": ctx.max_buckets}}},
            }
            data = ctx.os_client._search(ctx.index, body)
            buckets = data.get("aggregations", {}).get("top", {}).get("buckets", [])
            by_org.append({
                "organization": s.org_name,
                "values": [{"value": b["key"], "count": b["doc_count"]} for b in buckets],
            })
        return ToolResult(content={"field": field_name, "by_org": by_org}, summary=f"top {field_name}")

    return ToolSpec(
        name="top_values",
        description="Behavioral lens: the most common values of an allowlisted field per org "
                    f"(e.g. source IPs, images). Allowed fields: {', '.join(_TOP_VALUE_FIELDS)}.",
        parameters={"type": "object", "properties": {
            "field": {"type": "string", "enum": _TOP_VALUE_FIELDS},
        }, "required": ["field"]},
        executor=executor,
    )


def _agent_activity(ctx: HuntContext):
    def executor(args):
        agent_id = str((args or {}).get("agent_id") or "").strip()
        if not agent_id:
            return ToolResult(error="agent_id is required", summary="bad args")
        by_org, total = [], 0
        for s in ctx.scope:
            if agent_id not in s.agent_ids:
                continue  # tenant isolation: only query the org that owns this agent
            body = {
                "query": {"bool": {"filter": [
                    {"term": {"agent.id": agent_id}}, _time_filter(ctx.lookback_days),
                ]}},
                "sort": [{"@timestamp": {"order": "desc"}}],
                "size": ctx.max_findings_per_org,
            }
            data = ctx.os_client._search(ctx.index, body)
            hits = _hits(data)
            if hits:
                if ctx.record_findings:
                    ctx.record_findings(s, "agent_activity", hits)
                by_org.append({"organization": s.org_name, "count": len(hits)})
                total += len(hits)
        return ToolResult(
            content={"agent_id": agent_id, "by_org": by_org, "total": total},
            summary=f"{total} recent events for agent {agent_id}", count=total,
        )

    return ToolSpec(
        name="agent_activity",
        description="Behavioral lens: recent raw events for a single agent (deep-dive a host that "
                    "looks suspicious). Records the events as Findings. Only the owning org is queried.",
        parameters={"type": "object", "properties": {
            "agent_id": {"type": "string", "description": "Wazuh agent id to inspect."},
        }, "required": ["agent_id"]},
        executor=executor,
    )


def _agent_processes(ctx: HuntContext):
    def executor(args):
        agent_id = str((args or {}).get("agent_id") or "").strip()
        if not agent_id:
            return ToolResult(error="agent_id is required", summary="bad args")
        if not any(agent_id in s.agent_ids for s in ctx.scope):
            return ToolResult(error="agent not in hunt scope", summary="out of scope")
        try:
            procs = ctx.wazuh_client.get_agent_processes(agent_id)
        except Exception as exc:
            return ToolResult(error=f"could not fetch processes: {exc}", summary="error")
        return ToolResult(content={"agent_id": agent_id, "processes": procs},
                          summary=f"{len(procs)} processes on {agent_id}", count=len(procs))

    return ToolSpec(
        name="agent_processes",
        description="Behavioral lens: live running processes on an agent (syscollector).",
        parameters={"type": "object", "properties": {
            "agent_id": {"type": "string"},
        }, "required": ["agent_id"]},
        executor=executor,
    )


def _agent_ports(ctx: HuntContext):
    def executor(args):
        agent_id = str((args or {}).get("agent_id") or "").strip()
        if not agent_id:
            return ToolResult(error="agent_id is required", summary="bad args")
        if not any(agent_id in s.agent_ids for s in ctx.scope):
            return ToolResult(error="agent not in hunt scope", summary="out of scope")
        try:
            ports = ctx.wazuh_client.get_agent_ports(agent_id)
        except Exception as exc:
            return ToolResult(error=f"could not fetch ports: {exc}", summary="error")
        return ToolResult(content={"agent_id": agent_id, "ports": ports},
                          summary=f"{len(ports)} open ports on {agent_id}", count=len(ports))

    return ToolSpec(
        name="agent_ports",
        description="Behavioral lens: open ports / listening services on an agent (syscollector).",
        parameters={"type": "object", "properties": {
            "agent_id": {"type": "string"},
        }, "required": ["agent_id"]},
        executor=executor,
    )


def build_ioc_tools(ctx: HuntContext) -> List[ToolSpec]:
    """The minimal spine lens set (#476): IOC sweep only."""
    return [_ioc_search(ctx)]


def build_behavioral_tools(ctx: HuntContext) -> List[ToolSpec]:
    """The behavioral lens family (#480)."""
    return [
        _top_rules(ctx), _event_histogram(ctx), _top_values(ctx),
        _agent_activity(ctx), _agent_processes(ctx), _agent_ports(ctx),
    ]


def build_hunt_lenses(ctx: HuntContext, include_behavioral: bool = True) -> List[ToolSpec]:
    tools = build_ioc_tools(ctx)
    if include_behavioral:
        tools += build_behavioral_tools(ctx)
    return tools
