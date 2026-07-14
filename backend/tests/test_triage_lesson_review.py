"""Staff-only Triage Lesson review queue: service + API (ADR-0030/0031, slice #662)."""
import pytest

from incidents.memory import review
from incidents.memory.lessons import select_lessons
from incidents.models import Incident, Subject, TriageLesson
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def member_user(db, django_user_model):
    return django_user_model.objects.create_user(username="cust", password="p")


def make_incident(acme, subject=None):
    n = Incident.objects.count()
    return Incident.objects.create(organization=acme, title="x",
                                   display_id=f"INC-2026-{n + 1:04d}", subject=subject,
                                   state="triaged")


def proposed(org, subject, **kw):
    return TriageLesson.objects.create(organization=org, subject=subject, guidance="g",
                                       status="proposed", provenance="agent_proposed", **kw)


# ── service ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_approve_applies_edits_and_activates(acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.approve_lesson(lesson, staff=staff_user, edits={"guidance": "scrubbed guidance"})
    lesson.refresh_from_db()
    assert lesson.status == "active"
    assert lesson.guidance == "scrubbed guidance"
    assert lesson.approved_by_id == staff_user.id


@pytest.mark.django_db
def test_approved_lesson_becomes_selectable(acme, brute, staff_user):
    lesson = proposed(acme, brute)
    inc = make_incident(acme, subject=brute)
    assert select_lessons(inc) == []  # inert while proposed
    review.approve_lesson(lesson, staff=staff_user)
    assert [l.id for l in select_lessons(inc)] == [lesson.id]


@pytest.mark.django_db
def test_suspend_is_retroactive_safe(acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.approve_lesson(lesson, staff=staff_user)
    inc = make_incident(acme, subject=brute)
    assert [l.id for l in select_lessons(inc)] == [lesson.id]
    review.suspend_lesson(lesson, staff=staff_user)
    assert select_lessons(inc) == []  # never returned once suspended


@pytest.mark.django_db
def test_reject_archives(acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.reject_lesson(lesson, staff=staff_user)
    lesson.refresh_from_db()
    assert lesson.status == "archived"


@pytest.mark.django_db
def test_cannot_approve_archived(acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.reject_lesson(lesson, staff=staff_user)
    with pytest.raises(review.LessonReviewError):
        review.approve_lesson(lesson, staff=staff_user)


@pytest.mark.django_db
def test_author_lesson_is_active_immediately(brute, staff_user):
    lesson = review.author_lesson(subject=brute, guidance="write it", staff=staff_user)
    assert lesson.status == "active"
    assert lesson.provenance == "staff_authored"
    assert lesson.is_global is True  # organization=None => Global


# ── API ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_queue_requires_staff(client, member_user):
    client.force_login(member_user)
    assert client.get("/api/incidents/triage-lessons/").status_code == 403


@pytest.mark.django_db
def test_count_requires_staff(client, member_user):
    client.force_login(member_user)
    assert client.get("/api/incidents/triage-lessons/count/").status_code == 403


@pytest.mark.django_db
def test_count_returns_only_proposed(client, acme, brute, staff_user):
    proposed(acme, brute)
    proposed(acme, brute)
    active = proposed(acme, brute)
    review.approve_lesson(active, staff=staff_user)  # no longer proposed
    client.force_login(staff_user)
    res = client.get("/api/incidents/triage-lessons/count/")
    assert res.status_code == 200
    assert res.json() == {"count": 2}


@pytest.mark.django_db
def test_queue_lists_proposed_and_approve_activates(client, acme, brute, staff_user):
    lesson = proposed(acme, brute)
    client.force_login(staff_user)

    listed = client.get("/api/incidents/triage-lessons/").json()
    assert [row["id"] for row in listed] == [lesson.id]
    assert listed[0]["tier"] == "org"

    resp = client.post(f"/api/incidents/triage-lessons/{lesson.id}/approve/",
                       data={"guidance": "edited on approve"}, content_type="application/json")
    assert resp.status_code == 200
    lesson.refresh_from_db()
    assert lesson.status == "active"
    assert lesson.guidance == "edited on approve"


@pytest.mark.django_db
def test_api_suspend_and_reject(client, acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.approve_lesson(lesson, staff=staff_user)
    client.force_login(staff_user)
    assert client.post(f"/api/incidents/triage-lessons/{lesson.id}/suspend/").status_code == 200
    lesson.refresh_from_db()
    assert lesson.status == "suspended"


@pytest.mark.django_db
def test_api_author_global_lesson(client, brute, staff_user):
    client.force_login(staff_user)
    resp = client.post("/api/incidents/triage-lessons/",
                       data={"subject": brute.id, "guidance": "global heuristic"},
                       content_type="application/json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["tier"] == "global"
    assert body["status"] == "active"


@pytest.mark.django_db
def test_api_approve_conflict_on_archived(client, acme, brute, staff_user):
    lesson = proposed(acme, brute)
    review.reject_lesson(lesson, staff=staff_user)
    client.force_login(staff_user)
    resp = client.post(f"/api/incidents/triage-lessons/{lesson.id}/approve/")
    assert resp.status_code == 409
