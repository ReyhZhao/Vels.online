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

    return delegation


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

    return delegation
