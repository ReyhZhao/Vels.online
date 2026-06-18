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

logger = logging.getLogger(__name__)


TRIAGE_AGENT_SYS_PROMPT = (
    "You are the Triage Agent for a SOC. You are working a security incident that the "
    "triage classifier judged real and correctly classified, with HIGH confidence — so "
    "you act on it autonomously, with NO human watching. Work the incident:\n"
    "1. INVESTIGATE — use the read tools to gather context (related incidents and alerts "
    "in the same organisation, the assets involved, a host's installed software / "
    "services / processes), and you may search the public internet for threat "
    "intelligence. Stay within this incident's organisation.\n"
    "2. APPLY THE PLAYBOOK — call apply_task_template with the template_id of the matching "
    "playbook from available_templates (its tasks become the checklist of work).\n"
    "3. WORK THE MANUAL TASKS — for each manual task, research it and record your findings "
    "with add_task_comment. Never close a task; a human ratifies completion.\n"
    "4. RUN THE ACTIONABLE TASKS — use run_task to run the playbook's automated tasks. You "
    "may also run a wazuh_response task (e.g. isolate a host, block an IP) ONLY if it is "
    "pre-approved for autonomous execution; if run_task refuses it, recommend it in your "
    "summary for a human to run.\n"
    "5. ESCALATE / NOTIFY — if your research shows the incident is more serious than first "
    "classified, escalate to raise its severity. If the customer should be informed, "
    "send_contact_message with a clear non-technical update. You do NOT create detection "
    "exceptions and you do NOT close the incident — a human ratifies completion.\n"
    "When you have made what progress you can, STOP calling tools and write a concise "
    "summary of what you did, what you found, and what a human analyst should do next. Do "
    "not fabricate; if a lookup returns nothing, say so."
)


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


def _user_brief(grounding) -> str:
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
    return (
        "Work this incident. Here is its current state:\n\n"
        + json.dumps(brief, indent=2, default=str)
    )


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


def _handoff(incident, *, target_state, narrative, tool_trace, stop_reason, error=False):
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
        },
    )

    if target_state != incident.state and target_state in ALLOWED_TRANSITIONS.get(incident.state, set()):
        try:
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

    try:
        from incidents.llm.triage_tools import build_triage_tools
        tools = build_triage_tools(
            incident, grounding, include_web_search=not uses_native,
            os_client=os_client, wazuh_client=wazuh_client,
        )
        research = run_research_phase(
            provider, tools,
            [{"role": "system", "content": TRIAGE_AGENT_SYS_PROMPT},
             {"role": "user", "content": _user_brief(grounding)}],
            caps or triage_agent_caps(),
        )
        _handoff(
            incident,
            target_state=Incident.STATE_IN_PROGRESS,
            narrative=_final_narrative(research),
            tool_trace=research.tool_trace,
            stop_reason=research.stop_reason,
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
