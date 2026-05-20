from django.db import migrations


def seed(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    cron, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="2",
        day_of_month="*",
        month_of_year="*",
        day_of_week="*",
    )

    PeriodicTask.objects.get_or_create(
        name="auto-close-stale-incidents-daily",
        defaults={
            "task": "incidents.tasks.auto_close_stale_incidents",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="auto-close-stale-incidents-daily").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0003_add_advisory_refresh_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
