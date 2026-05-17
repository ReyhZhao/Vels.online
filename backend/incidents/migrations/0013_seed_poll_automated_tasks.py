from django.db import migrations


def seed_poll_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=30, period="seconds")
    PeriodicTask.objects.get_or_create(
        name="poll-automated-tasks",
        defaults={
            "task": "incidents.tasks.poll_automated_tasks",
            "interval": schedule,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="poll-automated-tasks").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("incidents", "0012_task_automation_fields"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.RunPython(seed_poll_task, reverse_seed),
    ]
