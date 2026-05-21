from django.db import migrations


def seed(apps, schema_editor):
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
        name="sync-wazuh-agents-daily",
        defaults={
            "task": "incidents.tasks.sync_wazuh_agents",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync-wazuh-agents-daily").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0004_add_auto_close_stale_incidents_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
