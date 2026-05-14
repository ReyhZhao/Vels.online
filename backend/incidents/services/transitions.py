from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.services.events import record_event

ALLOWED_TRANSITIONS = {
    "new":          {"triaged", "in_progress", "closed"},
    "triaged":      {"in_progress", "on_hold"},
    "in_progress":  {"on_hold", "resolved", "needs_tuning", "closed"},
    "on_hold":      {"in_progress", "resolved", "needs_tuning", "closed"},
    "needs_tuning": {"in_progress", "closed"},
    "resolved":     {"in_progress", "closed"},
    "closed":       {"in_progress"},
}

REOPEN_STATES = {"closed", "resolved", "needs_tuning"}


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

    _notify_state_change(incident, old_state, target_state)
    return incident


def _notify_state_change(incident, old_state, target_state):
    from incidents.models import IncidentDelegation
    from notifications.services.notifications import notify

    recipients = []
    if incident.assignee_id:
        try:
            recipients.append(User.objects.get(pk=incident.assignee_id))
        except User.DoesNotExist:
            pass

    delegate_ids = IncidentDelegation.objects.filter(
        incident=incident, returned_at__isnull=True
    ).values_list("user_id", flat=True)
    delegate_users = list(User.objects.filter(id__in=delegate_ids))
    all_recipients = list({u.id: u for u in recipients + delegate_users}.values())

    if all_recipients:
        notify(
            "state_change",
            all_recipients,
            incident=incident,
            payload={
                "title": f"{incident.display_id} state changed to {target_state}",
                "body": f"State changed from {old_state} to {target_state}.",
                "link": f"/incidents/{incident.id}",
            },
        )
