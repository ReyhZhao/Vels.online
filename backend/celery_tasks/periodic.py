"""Single source of truth for tasks intended to run on a schedule.

The project runs django_celery_beat's ``DatabaseScheduler`` with no static
``beat_schedule``: every periodic task must be seeded as a ``PeriodicTask`` row by
a data migration (see ``celery_tasks/migrations`` and each app's own seed
migrations). Nothing in Celery links a ``@shared_task`` to that seeding, so a task
meant to run on a schedule can silently never run if its seed migration is
forgotten — exactly bug #677 (the self-learning-Triage tasks from PRD #659).

``INTENDED_PERIODIC_TASKS`` closes that gap. Every dotted task path listed here is
asserted by ``tests/test_periodic_task_guard.py`` to have an enabled ``PeriodicTask``
row after migrations. When you add a new scheduled task:

1. add its ``@shared_task`` dotted path to this set, and
2. seed its schedule in a data migration (get_or_create a ``PeriodicTask`` row).

Omitting either step makes the guard test fail with a clear message.

Do NOT list tasks whose ``PeriodicTask`` rows are created dynamically at runtime
rather than seeded once (e.g. ``correlations.tasks.run_scheduled_search_rule``,
which gets a per-rule row when a Scheduled Search Rule is created/deleted). Those
have no fixed schedule to assert; the guard still checks their rows resolve to a
real registered Celery task via the separate orphan check.
"""

INTENDED_PERIODIC_TASKS = frozenset(
    {
        "attackmap.tasks.produce_attack_snapshot",
        "celery_tasks.tasks.cleanup_old_task_results",
        "correlations.tasks.run_detection_scan",
        "inbound_mail.tasks.poll_inbound_mail",
        "incidents.tasks.auto_close_stale_incidents",
        "incidents.tasks.cleanup_orphaned_attachments",
        "incidents.tasks.decay_stale_triage_lessons",
        "incidents.tasks.poll_automated_tasks",
        "incidents.tasks.run_triage_distillation_sweep",
        "incidents.tasks.send_assigned_incidents_digest",
        "incidents.tasks.sync_wazuh_agents",
        "incidents.tasks.update_classify_accuracy_metric",
        "notifications.tasks.cleanup_old_notifications",
        "partners.tasks.purge_intake_inbox",
        "security.tasks.generate_work_packages",
        "security.tasks.refresh_stale_advisories",
        "security.tasks.snapshot_vulnerabilities",
        "signups.tasks.expire_stale_invites",
    }
)
