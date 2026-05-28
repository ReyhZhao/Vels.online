from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.services.events import record_event


def transfer_incident(incident, new_assignee, actor):
    if not new_assignee.is_staff:
        raise ValidationError("new_assignee must be a staff user.")

    old_assignee = incident.assignee
    old_assignee_id = incident.assignee_id

    with transaction.atomic():
        incident.assignee = new_assignee
        incident.save(update_fields=["assignee"])
        record_event(
            incident,
            "incident_assignee_changed",
            actor=actor,
            payload={
                "from": old_assignee_id,
                "from_username": old_assignee.username if old_assignee else None,
                "to": new_assignee.id,
                "to_username": new_assignee.username,
            },
        )

    _notify_transfer(incident, new_assignee, old_assignee_id)
    return incident


def _notify_transfer(incident, new_assignee, old_assignee_id):
    from notifications.services.notifications import notify

    notify(
        "assignment",
        [new_assignee],
        incident=incident,
        payload={
            "title": f"{incident.display_id} assigned to you",
            "body": "You have been assigned to this incident.",
            "link": f"/incidents/{incident.id}",
        },
    )

    if old_assignee_id and old_assignee_id != new_assignee.id:
        try:
            old_assignee = User.objects.get(pk=old_assignee_id)
            notify(
                "assignment",
                [old_assignee],
                incident=incident,
                payload={
                    "title": f"{incident.display_id} reassigned",
                    "body": "You have been unassigned from this incident.",
                    "link": f"/incidents/{incident.id}",
                },
            )
        except User.DoesNotExist:
            pass
