"""Triage Lesson lifecycle hardening: auto-suspend, decay, consolidation (ADR-0030, #666)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from incidents.memory.lessons import (
    CONTRADICTION_SUSPEND_THRESHOLD, apply_contradiction, decay_stale_lessons,
    select_lessons,
)
from incidents.models import Incident, Subject, TriageLesson
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


def make_lesson(acme, brute, *, status="active", guidance="a distinctive heuristic here",
                last_applied_at=None):
    return TriageLesson.objects.create(organization=acme, subject=brute, status=status,
                                       guidance=guidance, provenance="staff_authored",
                                       last_applied_at=last_applied_at)


def make_incident(acme, brute):
    n = Incident.objects.count()
    return Incident.objects.create(organization=acme, title="x", display_id=f"INC-2026-{n + 1:04d}",
                                   subject=brute, state="triaged")


# ── contradiction auto-suspend ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_first_contradiction_does_not_suspend(acme, brute):
    lesson = make_lesson(acme, brute)
    apply_contradiction(lesson)
    lesson.refresh_from_db()
    assert lesson.contradiction_count == 1
    assert lesson.status == "active"


@pytest.mark.django_db
def test_reaching_threshold_auto_suspends(acme, brute):
    lesson = make_lesson(acme, brute)
    for _ in range(CONTRADICTION_SUSPEND_THRESHOLD):
        apply_contradiction(lesson)
    lesson.refresh_from_db()
    assert lesson.status == "suspended"
    # and it stops being selectable
    inc = make_incident(acme, brute)
    assert select_lessons(inc) == []


# ── decay ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_decay_archives_unused_active_lesson(acme, brute):
    old = timezone.now() - timedelta(days=200)
    stale = make_lesson(acme, brute, last_applied_at=old)
    fresh = make_lesson(acme, brute, guidance="fresh distinct guidance words",
                        last_applied_at=timezone.now())
    archived = decay_stale_lessons()
    assert archived == 1
    stale.refresh_from_db(); fresh.refresh_from_db()
    assert stale.status == "archived"
    assert fresh.status == "active"


@pytest.mark.django_db
def test_never_applied_but_recent_survives(acme, brute):
    # last_applied_at null but updated recently => not stale.
    lesson = make_lesson(acme, brute, last_applied_at=None)
    assert decay_stale_lessons() == 0
    lesson.refresh_from_db()
    assert lesson.status == "active"


# ── consolidation keeps the cap meaningful ──────────────────────────────────────────


@pytest.mark.django_db
def test_consolidation_keeps_within_cap(acme, brute):
    # Five near-identical + one distinct: consolidation collapses the dupes.
    for _ in range(5):
        make_lesson(acme, brute, guidance="verify the source address is internal before acting")
    make_lesson(acme, brute, guidance="page the on-call when a domain admin locks out")
    inc = make_incident(acme, brute)
    picked = select_lessons(inc, cap=5)
    guidances = {l.guidance for l in picked}
    assert len(guidances) == 2  # duplicates consolidated to one + the distinct one
