from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.services.events import record_event

ALLOWED_TRANSITIONS = {
    "new":         {"triaged", "in_progress"},
    "triaged":     {"in_progress", "on_hold"},
    "in_progress": {"on_hold", "resolved", "closed"},
    "on_hold":     {"in_progress", "resolved", "closed"},
    "resolved":    {"in_progress", "closed"},
    "closed":      {"in_progress"},
}

REOPEN_STATES = {"closed", "resolved"}


def transition_incident(incident, target_state, actor, closure_reason=None):
    allowed = ALLOWED_TRANSITIONS.get(incident.state, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition from '{incident.state}' to '{target_state}'."
        )

    if target_state == "closed" and not closure_reason:
        raise ValidationError("closure_reason is required when closing an incident.")

    old_state = incident.state
    old_closure_reason = incident.closure_reason

    with transaction.atomic():
        changes = {"state": {"old": old_state, "new": target_state}}
        incident.state = target_state

        if target_state == "closed":
            changes["closure_reason"] = {"old": old_closure_reason, "new": closure_reason}
            incident.closure_reason = closure_reason
        elif target_state == "in_progress" and old_state in REOPEN_STATES and old_closure_reason is not None:
            changes["closure_reason"] = {"old": old_closure_reason, "new": None}
            incident.closure_reason = None

        incident.save()
        record_event(incident, "incident_updated", actor=actor, payload={"changes": changes})

    return incident
