from django.db import migrations


def seed_advisory_refresh(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    cron, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_month="*",
        month_of_year="*",
        day_of_week="*",
    )

    PeriodicTask.objects.get_or_create(
        name="refresh-stale-advisories-nightly",
        defaults={
            "task": "security.tasks.refresh_stale_advisories",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="refresh-stale-advisories-nightly").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("celery_tasks", "0002_add_incident_digest_schedule"),
    ]

    operations = [
        migrations.RunPython(seed_advisory_refresh, reverse_seed),
    ]
