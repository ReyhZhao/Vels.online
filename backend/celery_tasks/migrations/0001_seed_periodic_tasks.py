import os

from django.db import migrations


DAILY_TASKS = [
    ("snapshot-vulnerabilities-daily", "security.tasks.snapshot_vulnerabilities"),
    ("cleanup-orphaned-attachments-daily", "incidents.tasks.cleanup_orphaned_attachments"),
    ("cleanup-old-notifications-daily", "notifications.tasks.cleanup_old_notifications"),
    ("expire-stale-invites-nightly", "signups.tasks.expire_stale_invites"),
    ("cleanup-old-task-results-nightly", "celery_tasks.tasks.cleanup_old_task_results"),
]


def seed_periodic_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    daily, _ = IntervalSchedule.objects.get_or_create(every=24, period="hours")

    cron_str = os.environ.get("WORK_PACKAGE_CRON_SCHEDULE", "0 6 * * 1")
    minute, hour, dom, month, dow = cron_str.split()
    work_cron, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_month=dom,
        month_of_year=month,
        day_of_week=dow,
    )

    for name, task in DAILY_TASKS:
        PeriodicTask.objects.get_or_create(
            name=name,
            defaults={"task": task, "interval": daily, "enabled": True},
        )

    PeriodicTask.objects.get_or_create(
        name="generate-work-packages-weekly",
        defaults={
            "task": "security.tasks.generate_work_packages",
            "crontab": work_cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    names = [name for name, _ in DAILY_TASKS] + ["generate-work-packages-weekly"]
    PeriodicTask.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(seed_periodic_tasks, reverse_seed),
    ]
