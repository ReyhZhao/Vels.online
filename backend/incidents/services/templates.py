from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from incidents.models import IncidentTemplateApplication, Task, TaskTemplate
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

        for item in template.items.select_related("automation").all():
            Task.objects.create(
                incident=incident,
                template_item=item,
                title=item.title,
                description=item.description,
                display_order=item.display_order,
                automation=item.automation,
                task_type=Task.TYPE_AUTOMATED if item.automation_id else Task.TYPE_MANUAL,
            )

        event_kind = "incident_template_reapplied" if previous else "incident_template_applied"
        record_event(
            incident,
            event_kind,
            actor=actor,
            payload={"template_id": template.id, "template_name": template.name},
        )


def cancel_template_tasks_on_subject_change(incident, old_subject, actor):
    """Cancel state=new tasks that came from old_subject's templates. Returns cancelled task ids."""
    qs = Task.objects.filter(
        incident=incident,
        state=Task.STATE_NEW,
        template_item__template__subject=old_subject,
    )
    cancelled_ids = list(qs.values_list("id", flat=True))
    if cancelled_ids:
        qs.update(state=Task.STATE_CANCELLED, closed_at=timezone.now())
        record_event(
            incident,
            "tasks_auto_cancelled",
            actor=actor,
            payload={
                "old_subject_slug": old_subject.slug,
                "cancelled_task_ids": cancelled_ids,
                "count": len(cancelled_ids),
            },
        )
    return cancelled_ids


def auto_apply_for_subject(incident, actor):
    """Apply all is_auto_apply=True templates for incident.subject. Silently skips idempotency failures."""
    if not incident.subject:
        return []
    templates = TaskTemplate.objects.filter(
        subject=incident.subject,
        is_auto_apply=True,
        archived=False,
    )
    applied = []
    for template in templates:
        try:
            apply_template(incident, template, actor)
            applied.append(template.name)
        except ValidationError:
            pass
    return applied
