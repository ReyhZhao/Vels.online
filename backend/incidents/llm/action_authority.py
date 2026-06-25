"""Incident-assistant action authority classifier (ADR-0012).

Actions split on two axes — externally visible? and lifecycle/severity/disclosure-
affecting? An action auto-executes only when neither is true; otherwise it is a
proposal the analyst confirms. The auto-execute set is exposed to the model as write
tools (executed in phase 1); the propose set comes out of the phase-2 envelope.

This module is the single source of truth for the split, used both to build the
write-tool set and as a guard so a mis-registered high-risk action can never auto-run.
"""

# Internal, reversible, non-lifecycle — safe to auto-execute.
AUTO_EXECUTE_ACTIONS = frozenset({
    "add_internal_comment",
    "self_assign",
    "add_tag",
    "link_known_asset",
    "add_task_comment",
})

# Externally visible OR lifecycle/severity/disclosure-affecting — must be proposed.
PROPOSE_ACTIONS = frozenset({
    "transition_state",
    "update_field",
    "apply_task_template",
    "send_contact_message",
    "create_exception",
    "close",
    # Generating an outward-facing Report must be confirmed by the analyst (ADR-0029);
    # the Triage Agent never generates Reports (ADR-0025 boundary holds).
    "propose_generate_report",
})


def is_auto_executable(action_type: str) -> bool:
    return action_type in AUTO_EXECUTE_ACTIONS


def is_proposable(action_type: str) -> bool:
    return action_type in PROPOSE_ACTIONS


def task_workable_by_assistant(task, incident) -> bool:
    """May the incident assistant autonomously work this task?

    Only `manual` tasks belonging to the bound incident — never `automated` or
    `wazuh_response` tasks (those touch live infrastructure and must be proposed/
    run by a human, ADR-0013). The single source of truth for the `add_task_comment`
    tool's guard.
    """
    from incidents.models import Task

    return (
        task is not None
        and task.incident_id == incident.id
        and task.task_type == Task.TYPE_MANUAL
    )
