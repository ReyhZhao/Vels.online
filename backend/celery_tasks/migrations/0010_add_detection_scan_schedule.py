from django.db import migrations


def seed(apps, schema_editor):
    """Seed the Detection Scan schedule (PRD #727, ADR-0036; closes #722).

    The Scan replaces the never-scheduled ``run_residual_safety_net`` — any row
    pointing at the dead task is removed so an obsoleted path can never run.
    """
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    PeriodicTask.objects.filter(task="correlations.tasks.run_residual_safety_net").delete()

    cron, _ = CrontabSchedule.objects.get_or_create(
        minute="20", hour="*", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="detection-scan-hourly",
        defaults={
            "task": "correlations.tasks.run_detection_scan",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="detection-scan-hourly").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0009_add_purge_intake_inbox_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
