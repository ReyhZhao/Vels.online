import os

from django.db import migrations


def seed_incident_digest(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    cron_str = os.environ.get("INCIDENT_DIGEST_CRON_SCHEDULE", "0 7 * * *")
    minute, hour, dom, month, dow = cron_str.split()
    cron, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_month=dom,
        month_of_year=month,
        day_of_week=dow,
    )

    PeriodicTask.objects.get_or_create(
        name="send-incident-digest-daily",
        defaults={
            "task": "incidents.tasks.send_assigned_incidents_digest",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="send-incident-digest-daily").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("celery_tasks", "0001_seed_periodic_tasks"),
    ]

    operations = [
        migrations.RunPython(seed_incident_digest, reverse_seed),
    ]
