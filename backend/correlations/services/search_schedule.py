"""Lifecycle management for per-rule PeriodicTask entries."""
import json
import logging

logger = logging.getLogger(__name__)

_TASK_NAME_PREFIX = "search_rule_"
_CELERY_TASK = "correlations.tasks.run_scheduled_search_rule"


def _task_name(rule) -> str:
    return f"{_TASK_NAME_PREFIX}{rule.id}"


def sync_rule_schedule(rule) -> None:
    """Create or update the PeriodicTask for rule; disable it if the rule is disabled."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    name = _task_name(rule)

    if not rule.enabled:
        PeriodicTask.objects.filter(name=name).update(enabled=False)
        return

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=rule.interval_minutes,
        period=IntervalSchedule.MINUTES,
    )

    PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            "task": _CELERY_TASK,
            "interval": schedule,
            "kwargs": json.dumps({"rule_id": rule.id}),
            "enabled": True,
        },
    )


def delete_rule_schedule(rule) -> None:
    """Remove the PeriodicTask for rule (called on rule deletion)."""
    from django_celery_beat.models import PeriodicTask

    PeriodicTask.objects.filter(name=_task_name(rule)).delete()
