"""Triage Lesson store + selection + Work-phase injection (ADR-0030/0031, slice #661)."""
import pytest

from incidents.memory.lessons import (
    lessons_brief, propose_lesson, record_applied, select_lessons,
)
from incidents.models import Incident, Subject, TriageLesson
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def globex(db):
    return Organization.objects.create(name="Globex", slug="globex", wazuh_group="globex")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


@pytest.fixture
def malware(db):
    subj, _ = Subject.objects.get_or_create(slug="malware", defaults={"name": "Malware"})
    return subj


def make_incident(org, *, subject=None, source_kind="wazuh_event"):
    n = Incident.objects.count()
    return Incident.objects.create(
        organization=org, title="x", display_id=f"INC-2026-{n + 1:04d}",
        subject=subject, source_kind=source_kind, state="triaged",
    )


def make_lesson(org, subject, *, status="active", guidance="g", source_kind="",
                provenance="staff_authored", applied_count=0):
    return TriageLesson.objects.create(
        organization=org, subject=subject, status=status, guidance=guidance,
        source_kind=source_kind, provenance=provenance, applied_count=applied_count,
    )


# ── selection: subject + status + scope ─────────────────────────────────────────


@pytest.mark.django_db
def test_selects_active_org_and_global_lessons_for_subject(acme, brute):
    org_lesson = make_lesson(acme, brute, guidance="org one")
    global_lesson = make_lesson(None, brute, guidance="global one")
    inc = make_incident(acme, subject=brute)

    picked = select_lessons(inc)
    assert {l.id for l in picked} == {org_lesson.id, global_lesson.id}


@pytest.mark.django_db
def test_excludes_non_active_lessons(acme, brute):
    make_lesson(acme, brute, status="proposed", guidance="proposed")
    make_lesson(acme, brute, status="suspended", guidance="suspended")
    active = make_lesson(acme, brute, status="active", guidance="active")
    inc = make_incident(acme, subject=brute)
    assert [l.id for l in select_lessons(inc)] == [active.id]


@pytest.mark.django_db
def test_excludes_other_subjects(acme, brute, malware):
    make_lesson(acme, malware, guidance="malware")
    inc = make_incident(acme, subject=brute)
    assert select_lessons(inc) == []


@pytest.mark.django_db
def test_never_returns_another_orgs_org_lesson(acme, globex, brute):
    make_lesson(globex, brute, guidance="foreign org")
    keep = make_lesson(None, brute, guidance="global keep")
    inc = make_incident(acme, subject=brute)
    assert [l.id for l in select_lessons(inc)] == [keep.id]


@pytest.mark.django_db
def test_source_kind_narrowing(acme, brute):
    any_kind = make_lesson(acme, brute, source_kind="", guidance="applies to any origin")
    match = make_lesson(acme, brute, source_kind="scheduled_search",
                        guidance="scheduled search specific guidance")
    make_lesson(acme, brute, source_kind="correlation",
                guidance="correlation rule specific guidance")
    inc = make_incident(acme, subject=brute, source_kind="scheduled_search")
    assert {l.id for l in select_lessons(inc)} == {any_kind.id, match.id}


@pytest.mark.django_db
def test_no_subject_returns_empty(acme, brute):
    make_lesson(acme, brute, guidance="g")
    inc = make_incident(acme, subject=None)
    assert select_lessons(inc) == []


@pytest.mark.django_db
def test_cap_limits_injection(acme, brute):
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    for w in words:
        make_lesson(acme, brute, guidance=f"heuristic about {w} traffic patterns")
    inc = make_incident(acme, subject=brute)
    assert len(select_lessons(inc, cap=5)) == 5


@pytest.mark.django_db
def test_consolidates_near_duplicates(acme, brute):
    make_lesson(None, brute, guidance="verify the source ip is internal before escalating")
    make_lesson(acme, brute, guidance="verify the source ip is internal before escalating",
                applied_count=9)
    inc = make_incident(acme, subject=brute)
    picked = select_lessons(inc)
    assert len(picked) == 1
    assert picked[0].organization_id == acme.id  # the org lesson shadows the identical global


# ── authoring + application bookkeeping ─────────────────────────────────────────


@pytest.mark.django_db
def test_propose_lesson_creates_proposed_row(acme, brute):
    inc = make_incident(acme, subject=brute)
    lesson = propose_lesson(inc, guidance="new heuristic", provenance="agent_proposed",
                            evidence=[inc])
    assert lesson.status == "proposed"
    assert lesson.organization_id == acme.id
    assert list(lesson.evidence.all()) == [inc]
    # inert: never selected while proposed
    assert select_lessons(inc) == []


@pytest.mark.django_db
def test_record_applied_bumps_count(acme, brute):
    l1 = make_lesson(acme, brute, guidance="a")
    record_applied([l1])
    l1.refresh_from_db()
    assert l1.applied_count == 1
    assert l1.last_applied_at is not None


@pytest.mark.django_db
def test_brief_renders_and_empty_is_blank(acme, brute):
    inc = make_incident(acme, subject=brute)
    make_lesson(acme, brute, guidance="do the thing", source_kind="")
    block = lessons_brief(select_lessons(inc))
    assert "do the thing" in block
    assert lessons_brief([]) == ""
