from django.db import migrations


def seed(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    cron, _ = CrontabSchedule.objects.get_or_create(
        minute="*/2",
        hour="*",
        day_of_month="*",
        month_of_year="*",
        day_of_week="*",
    )

    PeriodicTask.objects.get_or_create(
        name="poll-inbound-mail-every-2-min",
        defaults={
            "task": "inbound_mail.tasks.poll_inbound_mail",
            "crontab": cron,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="poll-inbound-mail-every-2-min").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0005_add_sync_wazuh_agents_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
