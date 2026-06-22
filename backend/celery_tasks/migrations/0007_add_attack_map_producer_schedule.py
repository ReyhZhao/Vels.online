from django.db import migrations


def seed(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # ~10s cadence (ADR-0027). Always scheduled but short-circuits instantly when no
    # viewer is present, so OpenSearch sees zero attack-map queries while idle.
    interval, _ = IntervalSchedule.objects.get_or_create(every=10, period="seconds")

    PeriodicTask.objects.get_or_create(
        name="attack-map-snapshot-every-10s",
        defaults={
            "task": "attackmap.tasks.produce_attack_snapshot",
            "interval": interval,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="attack-map-snapshot-every-10s").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0006_add_poll_inbound_mail_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
