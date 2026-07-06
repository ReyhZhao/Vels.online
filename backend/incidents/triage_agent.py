"""The agentic Triage Work phase — the Triage Agent (ADR-0024/0025).

Runs *only* on high disposition confidence with a matched subject, unattended, as a
background job. It reuses the shared agentic orchestrator (the same loop behind the
Incident Assistant and Hunt) to research the incident and then act on it. This module
owns the gate, the loop wiring, and the hand-off.

Slice 4 is research-only: read tools + PAP-gated web search, no mutations. The executed
write tools (apply playbook, work tasks, run tasks, notify/escalate) and the
pending_closure hand-off arrive in later slices.

The provider and infra clients are injectable so a turn is unit-testable with a scripted
provider and fake clients — no LLM, no OpenSearch, no Wazuh.
"""
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from assistants.orchestrator import LoopCaps, research_notes, run_research_phase

from incidents.llm.prompts import TRIAGE_AGENT_SYS_PROMPT

logger = logging.getLogger(__name__)


def triage_agent_caps() -> LoopCaps:
    """Relaxed background caps (a Celery worker removes proxy-timeout pressure)."""
    return LoopCaps(
        max_iterations=int(getattr(settings, "TRIAGE_AGENT_LOOP_MAX_ITERATIONS", 15)),
        per_tool_timeout_s=float(getattr(settings, "TRIAGE_AGENT_TOOL_TIMEOUT_S", 15.0)),
        deadline_s=float(getattr(settings, "TRIAGE_AGENT_LOOP_DEADLINE_S", 300.0)),
        max_auto_actions=int(getattr(settings, "TRIAGE_AGENT_MAX_AUTO_ACTIONS", 8)),
    )


def should_run_work_phase(incident, result) -> bool:
    """The gate (ADR-0024): high disposition confidence + a matched subject + not yet worked.

    `result` is the Classify phase's TriageResult. The caller must only invoke this when
    the incident was not auto-closed.
    """
    if incident.triage_worked_at is not None:
        return False
    if incident.subject_id is None:
        return False
    threshold = incident.organization.triage_work_threshold
    return getattr(result, "disposition_confidence", 0.0) >= threshold


def _final_narrative(research) -> str:
    """The model's closing summary is the last tool-free assistant text in the transcript."""
    for msg in reversed(research.messages):
        if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
            return msg["content"]
    return ""


def _user_brief(grounding, lessons_block="") -> str:
    import json
    inc = grounding.get("incident", {})
    brief = {
        "incident": inc,
        "assets": grounding.get("assets", []),
        "iocs": grounding.get("iocs", []),
        "linked_alerts": grounding.get("linked_alerts", []),
        "tasks": grounding.get("tasks", []),
        "available_templates": grounding.get("available_templates", []),
    }
    parts = [
        "Work this incident. Here is its current state:\n\n"
        + json.dumps(brief, indent=2, default=str)
    ]
    if lessons_block:
        parts.append("\n\n" + lessons_block)
    return "".join(parts)


def _ensure_assigned(incident):
    """Inherit the on-call assignment from Classify; if somehow unassigned, route now."""
    if incident.assignee_id:
        return
    from oncall.services.resolver import get_oncall_analyst
    analyst = get_oncall_analyst(at=timezone.now())
    if analyst is None:
        return
    incident.assignee = analyst
    incident.save(update_fields=["assignee", "updated_at"])
    from incidents.services.events import record_event
    record_event(incident, "assigned", actor=None,
                 payload={"assignee_id": analyst.id, "via": "triage_agent"})


def _handoff(incident, *, target_state, narrative, tool_trace, stop_reason, error=False,
             applied_lesson_ids=None):
    """Post the run summary, ensure on-call ownership, and land the incident's state."""
    from incidents.models import Comment
    from incidents.services.transitions import ALLOWED_TRANSITIONS, transition_incident

    _ensure_assigned(incident)

    body = narrative or (
        "The Triage Agent could not complete its research; a human should investigate."
        if error else "The Triage Agent completed its research; see findings."
    )
    Comment.objects.create(
        incident=incident,
        kind=Comment.KIND_AI_TRIAGE,
        author=None,
        body=body,
        is_internal=True,
        metadata={
            "triage_agent": True,
            "phase": "work",
            "tool_trace": tool_trace,
            "stop_reason": stop_reason,
            "error": error,
            "applied_lesson_ids": applied_lesson_ids or [],
        },
    )

    if target_state == incident.state:
        return
    try:
        if target_state in ALLOWED_TRANSITIONS.get(incident.state, set()):
            transition_incident(incident, target_state, actor=None)
        elif "in_progress" in ALLOWED_TRANSITIONS.get(incident.state, set()):
            # pending_closure is not directly reachable from triaged; go via in_progress.
            transition_incident(incident, "in_progress", actor=None)
            if target_state != "in_progress" and target_state in ALLOWED_TRANSITIONS.get(incident.state, set()):
                transition_incident(incident, target_state, actor=None)
    except ValidationError as exc:
        logger.warning("triage_agent: hand-off transition failed for %s: %s", incident.pk, exc)


def run_triage_work(incident_id, *, provider=None, os_client=None, wazuh_client=None, caps=None):
    """Execute the Triage Agent Work phase for one incident. Safe to call from Celery.

    Idempotent against re-entry via the durable triage_worked_at marker. Any error still
    hands the incident off safely (never left stuck) and sets the marker.
    """
    from incidents.models import Incident
    from incidents.llm.factory import get_assistant_provider
    from incidents.llm.grounding import build_incident_grounding

    try:
        incident = (
            Incident.objects.select_related("organization", "subject", "assignee")
            .prefetch_related("incident_assets__asset", "iocs", "tasks")
            .get(pk=incident_id)
        )
    except Incident.DoesNotExist:
        return

    # Durable once-per-incident guard (re-entry from Celery retries / linked alerts).
    if incident.triage_worked_at is not None:
        return

    try:
        provider = provider or get_assistant_provider()
    except Exception as exc:
        logger.warning("triage_agent: provider unavailable for %s: %s", incident_id, exc)
        incident.triage_worked_at = timezone.now()
        incident.save(update_fields=["triage_worked_at"])
        return

    # Mark worked up front so a crash mid-loop cannot cause an unbounded re-run. Set on
    # the in-memory instance (not a bare .update()) so the later hand-off save preserves it.
    incident.triage_worked_at = timezone.now()
    incident.save(update_fields=["triage_worked_at"])

    grounding = build_incident_grounding(incident)
    uses_native = getattr(provider, "uses_native_web_search", lambda: False)()

    # Inject the matched Subject's active Triage Lessons into the Work seed (ADR-0030,
    # slice #661). Best-effort — a memory failure never blocks the run.
    lessons_block = ""
    applied_lessons = []
    try:
        from incidents.memory.lessons import select_lessons, lessons_brief, record_applied
        applied_lessons = select_lessons(incident)
        lessons_block = lessons_brief(applied_lessons)
        record_applied(applied_lessons)
    except Exception as exc:
        logger.warning("triage_agent: lesson selection failed for %s: %s", incident_id, exc)

    try:
        from incidents.llm.triage_tools import build_triage_tools
        from incidents.presence_bridge import ai_presence, TRIAGE_AGENT_NAME
        contained = {"flag": False}
        tools = build_triage_tools(
            incident, grounding, include_web_search=not uses_native,
            os_client=os_client, wazuh_client=wazuh_client,
            on_contained=lambda: contained.update(flag=True),
        )
        # Surface this re-run as a live AI roster member while it works the incident
        # (PRD #605 slice #610). Dropped in the context manager's finally / TTL backstop.
        with ai_presence(incident.id, TRIAGE_AGENT_NAME) as ai:
            research = run_research_phase(
                provider, tools,
                [{"role": "system", "content": TRIAGE_AGENT_SYS_PROMPT},
                 {"role": "user", "content": _user_brief(grounding, lessons_block)}],
                caps or triage_agent_caps(),
                on_event=ai.on_event,
            )
        # The agent lands the incident in pending_closure when it judged the threat
        # contained, otherwise in_progress for a human to continue (ADR-0025).
        target_state = (
            Incident.STATE_PENDING_CLOSURE if contained["flag"] else Incident.STATE_IN_PROGRESS
        )
        _handoff(
            incident,
            target_state=target_state,
            narrative=_final_narrative(research),
            tool_trace=research.tool_trace,
            stop_reason=research.stop_reason,
            applied_lesson_ids=[l.id for l in applied_lessons],
        )
    except Exception as exc:
        logger.warning("triage_agent: work phase failed for %s: %s", incident_id, exc)
        _handoff(
            incident,
            target_state=Incident.STATE_IN_PROGRESS,
            narrative="",
            tool_trace=[],
            stop_reason="error",
            error=True,
        )
