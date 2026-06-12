"""Run a single Hunt turn (ADR-0015/0016, module 4).

Reuses the ADR-0011 agentic orchestrator (`run_research_phase`) but:
  - sources tools from the Hunt lens registry + native web search,
  - records matched docs as HuntFindings (the materialisable evidence),
  - writes every orchestrator event onto the Hunt's persisted, append-only event log
    (the SSE tail/replay source), and
  - drives status + cooperative cancel from the Hunt record (a dropped socket never
    cancels; only an explicit cancel does).

The provider/scope/clients are injectable so a turn is unit-testable with a scripted
provider and fake clients — no LLM, no OpenSearch, no Wazuh.
"""
import logging

from django.conf import settings
from django.db import transaction

from assistants.orchestrator import LoopCaps, run_research_phase
from assistants.web_search import build_web_search_tool, web_search_available

from .lenses import HuntContext, build_hunt_lenses
from .models import Hunt, HuntEvent, HuntFinding
from .scope import resolve_scope

logger = logging.getLogger(__name__)

HUNT_SYS_PROMPT = (
    "You are a threat-hunting assistant for a SOC. You are given a question or a "
    "malware/threat report. Identify the indicators of compromise (hashes, IPs, "
    "domains, filenames) and the behavioural patterns worth hunting, then use the "
    "lenses to check whether they appear across the customer fleet. Use ioc_search "
    "for specific indicators and the behavioural lenses (top_rules, event_histogram, "
    "top_values, agent_activity, agent_processes, agent_ports) for open-ended hunts. "
    "You may search the public internet for threat intelligence. When you have "
    "gathered enough, stop calling tools and write a concise summary of what you "
    "found, which organisations are affected, and what a human should investigate. "
    "You never take action on infrastructure; if an active response is warranted, "
    "recommend it in prose."
)


def hunt_caps() -> LoopCaps:
    """Relaxed caps for hunts (a background worker removes proxy-timeout pressure)."""
    return LoopCaps(
        max_iterations=int(getattr(settings, "HUNT_LOOP_MAX_ITERATIONS", 15)),
        per_tool_timeout_s=float(getattr(settings, "HUNT_TOOL_TIMEOUT_S", 15.0)),
        deadline_s=float(getattr(settings, "HUNT_LOOP_DEADLINE_S", 300.0)),
        max_auto_actions=int(getattr(settings, "HUNT_MAX_AUTO_ACTIONS", 8)),
    )


class _DbCancel:
    """Duck-typed threading.Event the orchestrator checks each iteration.

    Reads the Hunt's cancel_requested flag from the DB so an explicit cancel (set by
    the cancel endpoint) stops the loop — independent of any SSE connection.
    """
    def __init__(self, hunt_id):
        self.hunt_id = hunt_id

    def is_set(self):
        return Hunt.objects.filter(pk=self.hunt_id, cancel_requested=True).exists()


def _event_writer(hunt, turn):
    """Return an on_event callback that appends to the Hunt's event log."""
    state = {"seq": HuntEvent.objects.filter(hunt=hunt).count()}

    def append(event_type, data):
        seq = state["seq"]
        state["seq"] += 1
        HuntEvent.objects.create(hunt=hunt, seq=seq, turn=turn, type=event_type, data=data or {})
        return seq

    def on_event(event):
        etype = event.get("type", "tool")
        data = {k: v for k, v in event.items() if k != "type"}
        append(etype, data)

    on_event.append = append  # expose for result/error/done
    return on_event


def _collecting_sink(collected):
    """A findings sink that only appends to an in-memory list.

    Lenses run inside the orchestrator's per-tool worker thread; doing DB writes there
    can deadlock SQLite and is needless cross-thread work. So we collect during the loop
    and persist on the main thread afterwards (see _persist_findings).
    """
    def record(org_scope, lens_name, hits):
        for hit in hits:
            collected.append((org_scope.org_id, lens_name, hit))
    return record


def _persist_findings(hunt, collected):
    """Persist collected hits as HuntFindings on the main thread. Idempotent per doc."""
    from security.models import Organization

    org_cache = {}
    for org_id, lens_name, hit in collected:
        org = org_cache.get(org_id)
        if org is None:
            org = org_cache[org_id] = Organization.objects.get(pk=org_id)
        source = hit.get("_source", {}) or {}
        rule_desc = source.get("rule", {}).get("description", "") if isinstance(source, dict) else ""
        HuntFinding.objects.get_or_create(
            hunt=hunt,
            source_index=hit.get("_index", ""),
            wazuh_doc_id=hit.get("_id", ""),
            defaults={
                "organization": org,
                "lens": lens_name,
                "raw_doc": source,
                "summary": (rule_desc or lens_name)[:500],
            },
        )


def _final_narrative(research):
    """The model's closing summary is the last assistant text in the transcript."""
    for msg in reversed(research.messages):
        if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
            return msg["content"]
    return ""


def run_hunt_turn(
    hunt, messages, *, provider, scope=None, os_client=None, wazuh_client=None,
    include_behavioral=True, include_web_search=None, web_search_fn=None, caps=None,
):
    """Execute one hunt turn end to end, writing events to the Hunt's log.

    Returns the terminal status string. Safe to call from a Celery worker.
    """
    from security.opensearch import OpenSearchClient
    from security.wazuh import WazuhClient

    last_turn = HuntEvent.objects.filter(hunt=hunt).order_by("-turn").values_list("turn", flat=True).first()
    turn = (last_turn + 1) if last_turn is not None else 0

    on_event = _event_writer(hunt, turn)

    Hunt.objects.filter(pk=hunt.pk).update(status=Hunt.STATUS_RUNNING)

    try:
        scope = scope if scope is not None else resolve_scope(hunt, wazuh_client=wazuh_client)
        collected = []
        ctx = HuntContext(
            scope=scope,
            lookback_days=hunt.lookback_days,
            os_client=os_client or OpenSearchClient(),
            wazuh_client=wazuh_client or WazuhClient(),
            record_findings=_collecting_sink(collected),
        )
        tools = build_hunt_lenses(ctx, include_behavioral=include_behavioral)

        want_web = web_search_available() if include_web_search is None else include_web_search
        if want_web and not getattr(provider, "uses_native_web_search", lambda: False)():
            # Unrestricted web search for hunts (ADR-0015): no PAP guard. search_fn is
            # injectable so tests never hit the network.
            tools.append(build_web_search_tool(search_fn=web_search_fn))

        research = run_research_phase(
            provider, tools,
            [{"role": "system", "content": HUNT_SYS_PROMPT}] + messages,
            caps or hunt_caps(),
            on_event=on_event,
            cancel_event=_DbCancel(hunt.pk),
        )

        _persist_findings(hunt, collected)

        from .grouping import proposed_incidents
        if research.stop_reason == "client_gone":
            final_status = Hunt.STATUS_CANCELLED
        else:
            final_status = Hunt.STATUS_COMPLETED

        on_event.append("result", {
            "narrative": _final_narrative(research),
            "proposed_incidents": proposed_incidents(hunt),
            "findings_total": HuntFinding.objects.filter(hunt=hunt).count(),
            "stop_reason": research.stop_reason,
            "tool_trace": research.tool_trace,
        })
        clean_transcript = [m for m in research.messages if m.get("role") != "system"]
        Hunt.objects.filter(pk=hunt.pk).update(
            status=final_status, cancel_requested=False, transcript=clean_transcript,
        )
        on_event.append("done", {})
        return final_status

    except Exception as exc:  # any failure is terminal-in-stream
        logger.warning("run_hunt_turn failed for hunt %s: %s", hunt.pk, exc)
        on_event.append("error", {"detail": str(exc)})
        Hunt.objects.filter(pk=hunt.pk).update(status=Hunt.STATUS_ERROR)
        on_event.append("done", {})
        return Hunt.STATUS_ERROR
