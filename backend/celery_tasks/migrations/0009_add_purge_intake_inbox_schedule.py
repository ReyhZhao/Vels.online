from django.db import migrations


def seed(apps, schema_editor):
    """Seed the Intake Inbox retention purge (partner intake slice 7, #675)."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Daily off-peak; the task itself reads PARTNER_INTAKE_RETENTION_DAYS for the window.
    cron, _ = CrontabSchedule.objects.get_or_create(
        minute="15", hour="4", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="purge-intake-inbox-daily",
        defaults={
            "task": "partners.tasks.purge_intake_inbox",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="purge-intake-inbox-daily").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0008_add_self_learning_triage_schedules"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
