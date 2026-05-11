from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from incidents.services.events import record_event


def delegate(incident, user, by, note=""):
    if not user.is_staff:
        raise ValidationError("Delegate must be a staff user.")
    if incident.assignee_id and user.id == incident.assignee_id:
        raise ValidationError("Cannot delegate to the current assignee.")

    with transaction.atomic():
        from incidents.models import IncidentDelegation
        delegation = IncidentDelegation.objects.create(
            incident=incident,
            user=user,
            delegated_by=by,
            note=note,
        )
        record_event(
            incident,
            "incident_delegated",
            actor=by,
            payload={"delegate_id": user.id, "by_id": by.id, "note": note},
        )

    _notify_delegate(incident, user, note)
    return delegation


def _notify_delegate(incident, delegate_user, note):
    from notifications.services.notifications import notify

    notify(
        "delegation",
        [delegate_user],
        incident=incident,
        payload={
            "title": f"{incident.display_id} delegated to you",
            "body": note or "You have been delegated this incident.",
            "link": f"/incidents/{incident.id}",
        },
    )


def return_delegation(delegation, by):
    if delegation.returned_at is not None:
        raise ValidationError("Delegation has already been returned.")

    incident = delegation.incident
    if by.id != delegation.user_id and by.id != incident.assignee_id:
        raise ValidationError("Only the delegate or the incident assignee can return a delegation.")

    with transaction.atomic():
        delegation.returned_at = timezone.now()
        delegation.returned_by = by
        delegation.save(update_fields=["returned_at", "returned_by"])
        record_event(
            incident,
            "incident_delegation_returned",
            actor=by,
            payload={"delegate_id": delegation.user_id, "by_id": by.id},
        )

    _notify_delegation_returned(incident)
    return delegation


def _notify_delegation_returned(incident):
    from notifications.services.notifications import notify

    if not incident.assignee_id:
        return

    try:
        assignee = User.objects.get(pk=incident.assignee_id)
    except User.DoesNotExist:
        return

    notify(
        "assignment",
        [assignee],
        incident=incident,
        payload={
            "title": f"{incident.display_id} delegation returned",
            "body": "A delegation on this incident has been returned to you.",
            "link": f"/incidents/{incident.id}",
        },
    )
