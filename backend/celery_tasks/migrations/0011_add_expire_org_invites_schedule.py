from django.db import migrations


def seed(apps, schema_editor):
    """Seed the expire-stale-org-invites schedule (recurrence of #677/#722).

    ``security.tasks.expire_stale_org_invites`` shipped with the invite-user-to-org
    flow as a @shared_task but was never seeded and is never called on-demand, so it
    never ran under the DatabaseScheduler — pending OrgInvitations past their
    ``invite_expires_at`` were never marked EXPIRED. Nightly sweep mirrors its sibling
    ``signups.tasks.expire_stale_invites``.
    """
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="15", hour="4", day_of_month="*", month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="expire-stale-org-invites-nightly",
        defaults={
            "task": "security.tasks.expire_stale_org_invites",
            "crontab": nightly,
            "enabled": True,
        },
    )


def reverse_seed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="expire-stale-org-invites-nightly").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("celery_tasks", "0010_add_detection_scan_schedule"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_seed),
    ]
