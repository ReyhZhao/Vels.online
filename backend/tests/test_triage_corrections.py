"""Classification Correction capture + Classify-accuracy metric (ADR-0030, slice #665)."""
import pytest

from incidents.memory.corrections import (
    capture_classification_correction, classify_accuracy,
)
from incidents.memory.precedents import was_corrected
from incidents.models import ClassificationCorrection, Comment, Incident, Subject, TriageLesson
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


@pytest.fixture
def malware(db):
    subj, _ = Subject.objects.get_or_create(slug="malware", defaults={"name": "Malware"})
    return subj


@pytest.fixture
def analyst(db, django_user_model):
    return django_user_model.objects.create_user(username="a", password="p", is_staff=True)


def make_triaged(acme, *, subject=None, severity="medium",
                 agent_subject_slug="brute-force", agent_severity="medium",
                 applied_lesson_ids=None):
    """An incident that has been through Classify (carries the agent's baseline comment)."""
    n = Incident.objects.count()
    inc = Incident.objects.create(organization=acme, title="x", display_id=f"INC-2026-{n + 1:04d}",
                                  subject=subject, severity=severity, state="triaged")
    Comment.objects.create(
        incident=inc, kind=Comment.KIND_AI_TRIAGE, body="classify", is_internal=True,
        metadata={"subject_recommendation": agent_subject_slug,
                  "severity_recommendation": agent_severity,
                  "applied_lesson_ids": applied_lesson_ids or []},
    )
    return inc


# ── capture ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_subject_override_records_correction(acme, brute, malware, analyst):
    inc = make_triaged(acme, subject=malware, agent_subject_slug="brute-force")
    corr = capture_classification_correction(inc, actor=analyst, new_subject=malware)
    assert corr is not None
    assert corr.agent_subject.slug == "brute-force"
    assert corr.human_subject.slug == "malware"
    assert was_corrected(inc) is True


@pytest.mark.django_db
def test_agreeing_subject_records_nothing(acme, brute, analyst):
    inc = make_triaged(acme, subject=brute, agent_subject_slug="brute-force")
    corr = capture_classification_correction(inc, actor=analyst, new_subject=brute)
    assert corr is None
    assert ClassificationCorrection.objects.count() == 0


@pytest.mark.django_db
def test_severity_override_records_correction(acme, brute, analyst):
    inc = make_triaged(acme, subject=brute, agent_severity="low", severity="high")
    corr = capture_classification_correction(inc, actor=analyst, new_severity="high")
    assert corr is not None
    assert corr.agent_severity == "low"
    assert corr.human_severity == "high"


@pytest.mark.django_db
def test_no_baseline_records_nothing(acme, brute, malware, analyst):
    n = Incident.objects.count()
    inc = Incident.objects.create(organization=acme, title="x", display_id=f"INC-2026-{n + 1:04d}",
                                  subject=malware, state="triaged")  # never triaged
    assert capture_classification_correction(inc, actor=analyst, new_subject=malware) is None


@pytest.mark.django_db
def test_correction_contradicts_applied_lesson(acme, brute, malware, analyst):
    lesson = TriageLesson.objects.create(organization=acme, subject=brute, guidance="g",
                                         status="active", provenance="staff_authored")
    inc = make_triaged(acme, subject=malware, agent_subject_slug="brute-force",
                       applied_lesson_ids=[lesson.id])
    capture_classification_correction(inc, actor=analyst, new_subject=malware)
    lesson.refresh_from_db()
    assert lesson.contradiction_count == 1


# ── the accuracy metric ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_accuracy_counts_agreement(acme, brute, malware, analyst):
    # 2 agree (final subject == agent call), 1 disagrees.
    make_triaged(acme, subject=brute, agent_subject_slug="brute-force")
    make_triaged(acme, subject=brute, agent_subject_slug="brute-force")
    make_triaged(acme, subject=malware, agent_subject_slug="brute-force")

    stats = classify_accuracy()
    assert stats["total"] == 3
    assert stats["agreements"] == 2
    assert stats["accuracy"] == pytest.approx(2 / 3)


@pytest.mark.django_db
def test_accuracy_none_without_data(acme):
    stats = classify_accuracy()
    assert stats["total"] == 0
    assert stats["accuracy"] is None
