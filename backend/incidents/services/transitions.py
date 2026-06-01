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


def transition_incident(incident, target_state, actor, closure_reason=None, duplicate_of_id=None, assignee_id=None):
    from incidents.models import Incident

    allowed = ALLOWED_TRANSITIONS.get(incident.state, set())
    if target_state not in allowed:
        raise ValidationError(
            f"Cannot transition from '{incident.state}' to '{target_state}'."
        )

    if target_state == "closed" and not closure_reason:
        raise ValidationError("closure_reason is required when closing an incident.")

    if target_state == "closed" and closure_reason == "duplicate" and not duplicate_of_id:
        raise ValidationError("duplicate_of is required when closing as duplicate.")

    if target_state == "closed" and closure_reason != "duplicate" and duplicate_of_id:
        raise ValidationError("duplicate_of may only be set when closure_reason is duplicate.")

    canonical = None
    if duplicate_of_id:
        if duplicate_of_id == incident.pk:
            raise ValidationError("An incident cannot be marked as a duplicate of itself.")
        try:
            canonical = Incident.objects.get(pk=duplicate_of_id)
        except Incident.DoesNotExist:
            raise ValidationError("The referenced incident does not exist.")
        if canonical.organization_id != incident.organization_id:
            raise ValidationError("The referenced incident belongs to a different organisation.")

    old_state = incident.state
    old_closure_reason = incident.closure_reason
    old_duplicate_of_id = incident.duplicate_of_id

    with transaction.atomic():
        changes = {"state": {"old": old_state, "new": target_state}}
        incident.state = target_state

        if target_state == "closed":
            changes["closure_reason"] = {"old": old_closure_reason, "new": closure_reason}
            incident.closure_reason = closure_reason
            if canonical is not None:
                changes["duplicate_of"] = {"old": old_duplicate_of_id, "new": canonical.pk}
                incident.duplicate_of = canonical
        elif target_state == "in_progress" and old_state in REOPEN_STATES:
            if old_closure_reason is not None:
                changes["closure_reason"] = {"old": old_closure_reason, "new": None}
                incident.closure_reason = None
            if old_duplicate_of_id is not None:
                changes["duplicate_of"] = {"old": old_duplicate_of_id, "new": None}
                incident.duplicate_of = None

        if assignee_id is not None:
            old_assignee_id = incident.assignee_id
            if old_assignee_id != assignee_id:
                changes["assignee_id"] = {"old": old_assignee_id, "new": assignee_id}
                incident.assignee_id = assignee_id

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
