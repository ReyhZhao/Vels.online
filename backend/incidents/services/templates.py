from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.models import IncidentTemplateApplication, Task
from incidents.services.events import record_event


def apply_template(incident, template, actor):
    with transaction.atomic():
        active_count = Task.objects.filter(
            incident=incident,
            template_item__template=template,
            state__in=[Task.STATE_NEW, Task.STATE_IN_PROGRESS],
        ).count()
        if active_count > 0:
            raise ValidationError(
                "Template already applied and has active tasks. "
                "Complete or cancel all tasks from this template before re-applying."
            )

        previous = IncidentTemplateApplication.objects.filter(
            incident=incident, template=template
        ).exists()

        IncidentTemplateApplication.objects.create(
            incident=incident,
            template=template,
            applied_by=actor,
        )

        for item in template.items.all():
            Task.objects.create(
                incident=incident,
                template_item=item,
                title=item.title,
                description=item.description,
                display_order=item.display_order,
            )

        event_kind = "incident_template_reapplied" if previous else "incident_template_applied"
        record_event(
            incident,
            event_kind,
            actor=actor,
            payload={"template_id": template.id, "template_name": template.name},
        )
