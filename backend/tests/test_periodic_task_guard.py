"""Guard against periodic tasks that are never scheduled (bug #677 / issue #678).

Two independent checks over the ``PeriodicTask`` rows that migrations seed:

* **coverage** — every task path in ``INTENDED_PERIODIC_TASKS`` has an enabled row,
  so a task declared periodic can't ship without its schedule seeding.
* **no orphans** — every seeded row's ``task`` path resolves to a real registered
  Celery task, catching typos and renames that would silently stop a task running.
"""

import pytest
from django_celery_beat.models import PeriodicTask

from celery_tasks.periodic import INTENDED_PERIODIC_TASKS


def _registered_celery_tasks():
    """Dotted paths of every task Celery knows about, after app autodiscovery."""
    from config.celery import app

    app.loader.import_default_modules()
    return set(app.tasks.keys())


@pytest.mark.django_db
def test_every_intended_periodic_task_is_seeded():
    """Each intended-periodic task must have an enabled PeriodicTask row.

    If this fails, a task was added to INTENDED_PERIODIC_TASKS (or a @shared_task was
    meant to be periodic) without a data migration seeding its schedule — add a
    PeriodicTask.get_or_create in a celery_tasks (or owning app) data migration."""
    enabled = set(
        PeriodicTask.objects.filter(enabled=True).values_list("task", flat=True)
    )
    missing = sorted(INTENDED_PERIODIC_TASKS - enabled)
    assert not missing, (
        "Intended-periodic tasks have no enabled PeriodicTask row (schedule seeding "
        f"missing): {missing}. Seed each in a data migration."
    )


@pytest.mark.django_db
def test_no_seeded_task_points_at_an_unregistered_celery_task():
    """Every PeriodicTask row's task path must resolve to a registered Celery task.

    Catches typos/renames: a schedule that names a task Celery doesn't know about
    will never execute."""
    registered = _registered_celery_tasks()
    seeded = set(PeriodicTask.objects.values_list("task", flat=True))
    orphans = sorted(seeded - registered)
    assert not orphans, (
        "Seeded PeriodicTask rows reference tasks Celery does not know about "
        f"(typo/rename?): {orphans}."
    )


def test_intended_periodic_paths_are_registered_celery_tasks():
    """The registry itself must not drift from renamed/removed tasks."""
    registered = _registered_celery_tasks()
    unknown = sorted(INTENDED_PERIODIC_TASKS - registered)
    assert not unknown, (
        "INTENDED_PERIODIC_TASKS lists paths that are not registered Celery tasks "
        f"(renamed/removed?): {unknown}."
    )
