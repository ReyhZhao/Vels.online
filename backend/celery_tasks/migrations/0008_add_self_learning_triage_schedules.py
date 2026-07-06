from django.db import migrations


def seed(apps, schema_editor):
    """Seed the three self-learning-Triage periodic tasks (PRD #659, ADR-0030).

    These @shared_tasks in incidents.tasks were shipped without a beat schedule, so
    they never ran under the DatabaseScheduler (bug #677)."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Nightly batched distillation sweep — LLM-costly, so run once daily off-peak.
    nightly_sweep, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="3", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="run-triage-distillation-sweep-nightly",
        defaults={
            "task": "incidents.tasks.run_triage_distillation_sweep",
            "crontab": nightly_sweep,
            "enabled": True,
        },
    )

    # Nightly lesson decay/archival — cheap DB pass; sits just after the sweep.
    nightly_decay, _ = CrontabSchedule.objects.get_or_create(
        minute="30", hour="3", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="decay-stale-triage-lessons-nightly",
        defaults={
            "task": "incidents.tasks.decay_stale_triage_lessons",
            "crontab": nightly_decay,
            "enabled": True,
        },
    )

    # Classify-accuracy gauge — recompute hourly so the Prometheus metric stays fresh.
    hourly, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="*", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="update-classify-accuracy-metric-hourly",
        defaults={
            "task": "incidents.tasks.update_classify_accuracy_metric",
            "crontab": hourly,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        name__in=[
            "run-triage-distillation-sweep-nightly",
            "decay-stale-triage-lessons-nightly",
            "update-classify-accuracy-metric-hourly",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0007_add_attack_map_producer_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
