from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.services.events import record_event


def transfer_incident(incident, new_assignee, actor):
    if not new_assignee.is_staff:
        raise ValidationError("new_assignee must be a staff user.")

    old_assignee_id = incident.assignee_id

    with transaction.atomic():
        incident.assignee = new_assignee
        incident.save(update_fields=["assignee"])
        record_event(
            incident,
            "incident_assignee_changed",
            actor=actor,
            payload={"from": old_assignee_id, "to": new_assignee.id},
        )

    return incident
