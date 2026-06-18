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

# Reuse the assistant's host-inventory and manual-task-findings tools: both scope purely
# by the incident's organisation (never by user) and accept actor=None, so they are
# already correct for the unattended agent.
from incidents.llm.assistant_tools import _add_task_comment, _host_inventory, _record_autonomous
from incidents.llm.triage_action_authority import TRIAGE_AGENT_WRITE_ACTIONS

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


# ── write (executed) tools — ADR-0025 ─────────────────────────────────────────


def _apply_task_template(incident):
    def executor(args):
        from django.core.exceptions import ValidationError
        from incidents.models import TaskTemplate
        from incidents.services.templates import apply_template

        template_id = (args or {}).get("template_id")
        if template_id is None:
            return ToolResult(error="template_id is required", summary="missing template_id")
        if incident.subject_id is None:
            return ToolResult(error="incident has no subject; cannot apply a playbook",
                              summary="no subject")
        tmpl = (
            TaskTemplate.objects.filter(pk=template_id, archived=False)
            .select_related("subject").first()
        )
        if tmpl is None:
            return ToolResult(error="no such task template", summary="template not found")
        if tmpl.subject_id != incident.subject_id:
            return ToolResult(
                error="that template belongs to a different subject than this incident",
                summary="subject mismatch",
            )
        try:
            apply_template(incident, tmpl, actor=None)
        except ValidationError as exc:
            # Idempotency: apply_template refuses to re-apply a template with active tasks.
            return ToolResult(error=str(exc), summary="already applied")
        _record_autonomous(incident, None, "apply_task_template",
                           {"template_id": tmpl.id, "name": tmpl.name})
        return ToolResult(content={"applied": tmpl.name}, summary=f"applied playbook '{tmpl.name}'")
    return ToolSpec(
        name="apply_task_template", is_write=True,
        description="Apply one of this incident's available playbooks (task templates for its "
                    "subject), creating its tasks. Pass the template_id from available_templates in "
                    "context. This only CREATES the tasks; running automated/wazuh_response tasks is "
                    "a separate step.",
        parameters={"type": "object", "properties": {
            "template_id": {"type": "integer", "description": "Id of the template (from available_templates)."}},
            "required": ["template_id"]},
        executor=executor,
    )


def _run_task(incident):
    def executor(args):
        from incidents.models import Task
        from incidents.services import task_execution

        task_id = (args or {}).get("task_id")
        if task_id is None:
            return ToolResult(error="task_id is required", summary="missing task_id")
        task = (
            Task.objects.filter(pk=task_id, incident=incident)
            .select_related("incident", "automation", "wazuh_response").first()
        )
        if task is None:
            return ToolResult(error="no such task on this incident", summary="task not found")
        try:
            task = task_execution.run_task(task, actor=None, by_agent=True)
        except task_execution.TaskExecutionError as exc:
            return ToolResult(error=exc.message, summary=exc.code)
        _record_autonomous(incident, None, "run_task",
                           {"task_id": task.id, "task_title": task.title, "task_type": task.task_type})
        return ToolResult(content={"task_id": task.id, "state": task.state},
                          summary=f"ran task '{task.title}'")
    return ToolSpec(
        name="run_task", is_write=True,
        description="Run an AUTOMATED (Semaphore) or WAZUH_RESPONSE task on this incident. Automated "
                    "tasks run on your confidence; a wazuh_response (e.g. isolate a host, block an IP) "
                    "runs only if it has been pre-approved for autonomous execution — otherwise it is "
                    "refused and you should recommend it in your summary for a human to run. Only runs "
                    "a task that has not already been executed.",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "integer", "description": "Id of the automated/wazuh_response task."}},
            "required": ["task_id"]},
        executor=executor,
    )


def _send_contact_message(incident):
    def executor(args):
        from contacts.models import IncidentContact
        from contacts.services import send_contact_message

        message = ((args or {}).get("message") or "").strip()
        if not message:
            return ToolResult(error="message is required", summary="empty message")
        recipients = list(
            IncidentContact.objects.filter(incident=incident).select_related("contact")
        )
        if not recipients:
            return ToolResult(error="this incident has no contacts to notify", summary="no contacts")
        sent = 0
        for ic in recipients:
            try:
                send_contact_message(incident, ic.contact, role="notified", body=message)
                sent += 1
            except Exception:
                pass
        _record_autonomous(incident, None, "send_contact_message",
                           {"recipients": sent, "preview": message[:80]})
        return ToolResult(content={"sent": sent}, summary=f"notified {sent} contact(s)")
    return ToolSpec(
        name="send_contact_message", is_write=True,
        description="Notify this incident's contacts with a clear, non-technical message about the "
                    "incident (what happened, what is being done). Use sparingly and only when the "
                    "customer should be informed.",
        parameters={"type": "object", "properties": {
            "message": {"type": "string", "description": "The message body to send to the contacts."}},
            "required": ["message"]},
        executor=executor,
    )


def _escalate(incident):
    def executor(args):
        from incidents.llm.base import SEVERITY_RANK
        from incidents.services.notifications_wiring import notify_severity_bump_if_needed

        target = ((args or {}).get("severity") or "high").strip()
        reason = ((args or {}).get("reason") or "").strip()
        if target not in SEVERITY_RANK:
            return ToolResult(error=f"severity must be one of {', '.join(SEVERITY_RANK)}",
                              summary="bad severity")
        old = incident.severity
        if SEVERITY_RANK[target] <= SEVERITY_RANK.get(old, 0):
            return ToolResult(
                error=f"target severity '{target}' is not higher than current '{old}'",
                summary="no escalation needed",
            )
        incident.severity = target
        incident.save(update_fields=["severity", "updated_at"])
        notify_severity_bump_if_needed(incident, old)
        _record_autonomous(incident, None, "escalate",
                           {"old": old, "new": target, "reason": reason[:120]})
        return ToolResult(content={"severity": target}, summary=f"escalated {old} -> {target}")
    return ToolSpec(
        name="escalate", is_write=True,
        description="Raise this incident's severity (and page the org) when your research shows it is "
                    "more serious than first classified. Errs toward MORE human attention.",
        parameters={"type": "object", "properties": {
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
            "reason": {"type": "string", "description": "Why you are escalating."}},
            "required": ["severity"]},
        executor=executor,
    )


def _mark_threat_contained(incident, on_contained):
    def executor(args):
        reason = ((args or {}).get("reason") or "").strip()
        on_contained()
        _record_autonomous(incident, None, "mark_threat_contained", {"reason": reason[:120]})
        return ToolResult(content={"contained": True}, summary="marked threat contained")
    return ToolSpec(
        name="mark_threat_contained", is_write=True,
        description="Call this ONLY when you judge the threat CONTAINED — the playbook's "
                    "automated/response actions have run and your research is recorded — so the "
                    "incident is handed to a human only to verify and close (it lands in "
                    "'pending closure'). If meaningful work still remains, do NOT call this; the "
                    "incident will be handed off as in-progress for a human to continue.",
        parameters={"type": "object", "properties": {
            "reason": {"type": "string", "description": "Why you consider the threat contained."}}},
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


def build_triage_tools(incident, grounding, *, include_web_search=True, read_only=False,
                       os_client=None, wazuh_client=None, on_contained=None):
    """Full Triage Agent tool set: read tools (+ web search) plus the executed write tools.

    `read_only=True` returns only the read tools (the slice-4 research-only behaviour).
    Every write tool registered is asserted to be in TRIAGE_AGENT_WRITE_ACTIONS so a
    mis-registered higher-risk action can never reach the model (ADR-0025).
    """
    tools = build_triage_read_tools(
        incident, grounding, include_web_search=include_web_search,
        os_client=os_client, wazuh_client=wazuh_client,
    )
    if read_only:
        return tools

    write_tools = [
        _apply_task_template(incident),
        _add_task_comment(incident, None),
        _run_task(incident),
        _send_contact_message(incident),
        _escalate(incident),
        _mark_threat_contained(incident, on_contained or (lambda: None)),
    ]
    for t in write_tools:
        assert t.name in TRIAGE_AGENT_WRITE_ACTIONS, f"unauthorised triage write tool: {t.name}"
    return tools + write_tools
