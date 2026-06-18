"""Request-free execution of incident Tasks (ADR-0024).

The run logic used to live inside `TaskRunView`, coupled to `request`. It is
extracted here so both the staff-facing view (actor = a human, `by_agent=False`)
and the unattended Triage Agent (actor = None, `by_agent=True`) can run a task
through one path with identical permissions, validation, side effects and audit.

Two guards exist *only* for the agent (`by_agent=True`), never for a human:
  - the **task-state guard** — only a `state=new` task runs; an already-executed
    task is skipped, so a re-triggered agent re-researches but never re-isolates a
    host or re-blocks an IP.
  - the **autonomous-response approval** check — a `wazuh_response` runs unattended
    only when its catalog entry is `autonomous_triage_approved` (ADR-0025).

A human running a task from the UI is a deliberate act and keeps the historic
behaviour (no state guard, no approval gate) byte-for-byte.
"""
import logging

from django.db import transaction

from incidents.models import Comment, Incident, Task, WazuhResponseExecution
from incidents.services.events import record_event

logger = logging.getLogger(__name__)


class TaskExecutionError(Exception):
    """A task could not be executed. Carries an HTTP status for view adaptation."""

    def __init__(self, message, *, code, http_status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


def _actor_label(actor):
    return actor.username if actor is not None else "the Triage Agent"


def build_automated_extra_vars(task, vars_override=None):
    """Merge default_vars + resolved mappings + hardcoded incident fields.

    Raises TaskExecutionError(code='unresolvable_var') if a mapping resolves to
    nothing. `vars_override`, when a dict, is merged last (the editable-preview path).
    """
    from automations.incident_vars import UnresolvableVarError, resolve_incident_vars
    import yaml

    incident = task.incident
    extra_vars = {}
    if task.automation.default_vars:
        parsed = yaml.safe_load(task.automation.default_vars)
        if isinstance(parsed, dict):
            extra_vars.update(parsed)

    if task.automation.incident_var_mappings:
        incident = Incident.objects.prefetch_related("assets", "iocs").get(pk=incident.pk)
        try:
            extra_vars.update(resolve_incident_vars(task.automation.incident_var_mappings, incident))
        except UnresolvableVarError as exc:
            raise TaskExecutionError(
                f"Mapping for '{exc.var_name}' (source: {exc.source}) resolved to no values.",
                code="unresolvable_var",
                http_status=400,
            )

    extra_vars.update({
        "incident_id": incident.id,
        "incident_display_id": incident.display_id,
        "incident_title": incident.title,
        "incident_severity": incident.severity,
    })
    if isinstance(vars_override, dict):
        extra_vars.update(vars_override)
    return extra_vars


def execute_automated_task(task, *, actor, extra_vars):
    """Launch the task's Semaphore job and mark it in-progress. Returns the task.

    Raises TaskExecutionError(code='semaphore_error', http_status=502) on dispatch
    failure (mirroring the historic view behaviour).
    """
    from automations.semaphore import SemaphoreAPIError, SemaphoreClient

    try:
        client = SemaphoreClient()
        semaphore_task_id = client.launch_job(
            template_id=task.automation.semaphore_template_id,
            extra_vars=extra_vars,
        )
    except SemaphoreAPIError as exc:
        logger.exception(
            "launch_job failed for task=%s automation=%s template_id=%s: status=%s",
            task.pk, task.automation_id, task.automation.semaphore_template_id, exc.status_code,
        )
        raise TaskExecutionError(
            "Service error launching automation.", code="semaphore_error", http_status=502
        )

    update_fields = dict(
        semaphore_task_id=semaphore_task_id,
        state=Task.STATE_IN_PROGRESS,
        automation_error=None,
    )
    if not task.assignee_id and actor is not None:
        update_fields["assignee"] = actor
    Task.objects.filter(pk=task.pk).update(**update_fields)
    task.refresh_from_db()
    return task


def execute_wazuh_response_task(task, *, actor, args=None, agent_ids=None, timeout=None):
    """Dispatch the task's Wazuh active response and record it. Returns the task.

    `actor` may be None (the unattended Triage Agent). The dispatch, state update,
    WazuhResponseExecution row, system comment and timeline event mirror the historic
    view path exactly, with the actor label substituted.
    """
    from automations.interpolation import interpolate_args
    from security.wazuh import WazuhAPIError, WazuhClient

    if not task.wazuh_response_id:
        raise TaskExecutionError(
            "Task has no Wazuh response attached.", code="no_wazuh_response", http_status=400
        )

    wr = task.wazuh_response
    incident = Incident.objects.prefetch_related("assets", "iocs").get(pk=task.incident_id)

    override_args = (args or "").strip()
    resolved_args = override_args if override_args else interpolate_args(wr.default_args, incident)

    if agent_ids and isinstance(agent_ids, list):
        agent_ids = [str(a) for a in agent_ids]
    else:
        agent_ids = list(
            incident.assets.filter(agent_name__isnull=False).values_list("agent_name", flat=True)
        )

    timeout = int(timeout) if timeout is not None else wr.timeout

    wazuh_status_code = None
    wazuh_response_body = {}
    error_msg = None

    try:
        client = WazuhClient()
        wazuh_status_code, wazuh_response_body = client.run_active_response(
            command=wr.command, agent_ids=agent_ids, args=resolved_args, timeout=timeout,
        )
    except WazuhAPIError:
        logger.exception("WazuhAPIError running active response task=%s", task.pk)
        error_msg = "Active response failed; see server logs for details."

    with transaction.atomic():
        Task.objects.filter(pk=task.pk).update(
            state=Task.STATE_DONE,
            automation_error=error_msg,
            assignee=task.assignee or actor,
        )
        task.refresh_from_db()

        execution = WazuhResponseExecution.objects.create(
            wazuh_response=wr,
            executed_by=actor,
            agent_ids=agent_ids,
            resolved_args=resolved_args,
            timeout_used=timeout,
            incident=task.incident,
            task=task,
            wazuh_status_code=wazuh_status_code,
            wazuh_response_body=wazuh_response_body,
        )

        agents_str = ", ".join(agent_ids) if agent_ids else "no agents"
        actor_label = _actor_label(actor)
        if error_msg:
            body = (
                f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to {agents_str} "
                f"by {actor_label}. **Error:** {error_msg}"
            )
        else:
            body = (
                f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to {agents_str} "
                f"by {actor_label}. Status {wazuh_status_code} — dispatch confirmed "
                f"(not execution confirmed)."
            )
        Comment.objects.create(
            incident=task.incident,
            author=actor,
            body=body,
            kind=Comment.KIND_SYSTEM,
        )
        record_event(
            task.incident,
            "wazuh_response_dispatched",
            actor=actor,
            payload={
                "task_id": task.id,
                "wazuh_response_id": wr.id,
                "wazuh_response_name": wr.name,
                "command": wr.command,
                "agent_ids": agent_ids,
                "resolved_args": resolved_args,
                "timeout_used": timeout,
                "execution_id": execution.id,
                "status_code": wazuh_status_code,
                "error": error_msg,
                "autonomous": actor is None,
            },
        )
    return task


def run_task(task, *, actor, by_agent=False, args=None, agent_ids=None, timeout=None, vars_override=None):
    """High-level entry: run an automated or wazuh_response task, with the agent guards.

    For `by_agent=True` (the unattended Triage Agent): the task-state guard and the
    autonomous-response approval gate apply. For a human (`by_agent=False`) this is a
    thin dispatcher with neither guard, preserving the historic view behaviour.
    """
    if task.task_type == Task.TYPE_MANUAL:
        raise TaskExecutionError(
            "Manual tasks are not executable.", code="not_executable", http_status=400
        )

    if by_agent and task.state != Task.STATE_NEW:
        raise TaskExecutionError(
            f"Task {task.id} is already {task.state}; skipped to avoid re-execution.",
            code="already_executed",
            http_status=409,
        )

    if task.task_type == Task.TYPE_WAZUH_RESPONSE:
        if by_agent and not (task.wazuh_response_id and task.wazuh_response.autonomous_triage_approved):
            raise TaskExecutionError(
                "Wazuh response is not approved for autonomous execution.",
                code="not_approved",
                http_status=403,
            )
        return execute_wazuh_response_task(
            task, actor=actor, args=args, agent_ids=agent_ids, timeout=timeout
        )

    # automated
    if not task.automation_id:
        raise TaskExecutionError(
            "Task has no automation attached.", code="no_automation", http_status=400
        )
    extra_vars = build_automated_extra_vars(task, vars_override=vars_override)
    return execute_automated_task(task, actor=actor, extra_vars=extra_vars)
