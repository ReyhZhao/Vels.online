"""The unattended Triage Agent's executed-write authority (ADR-0025).

The Incident Assistant (ADR-0012/0013) splits actions into auto-execute vs propose
because a *human is present* to confirm the propose set. The Triage Agent has no human,
so it cannot "propose" — it either executes within this confidence-gated authority or
leaves the work for the routed analyst.

This module is the single source of truth for which write actions the agent may execute
as tools. `build_triage_tools` asserts every write tool it registers is named here, so a
mis-registered higher-risk action can never reach the model.
"""

# Write actions the Triage Agent executes within the confidence gate. Grows by slice:
#   slice 5 — apply_task_template, add_task_comment
#   slice 6 — run_task (automated always; wazuh_response only if autonomous_triage_approved)
#   slice 7 — send_contact_message, escalate
TRIAGE_AGENT_WRITE_ACTIONS = frozenset({
    "apply_task_template",
    "add_task_comment",
})

# Never executed by the agent — closing a real worked incident and silencing future
# detections stay human decisions (only Classify auto-closes, and only false positives).
TRIAGE_AGENT_NEVER_EXECUTE = frozenset({
    "create_exception",
    "close",
})


def is_triage_executable(action_type: str) -> bool:
    return action_type in TRIAGE_AGENT_WRITE_ACTIONS
