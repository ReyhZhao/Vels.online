"""Distillation-run observability (ADR-0030, #697).

The sweep skips most clusters silently; ``run_and_record_sweep`` persists an inspectable
DistillationRun capturing what each run considered and why it did or did not propose a
Lesson, surfaced staff-only on the Triage Lessons review page. Recording is purely
observational — it must not change which Lessons get proposed.
"""
import pytest
from rest_framework.test import APIClient

from incidents.memory.distillation import RUN_RETENTION, run_and_record_sweep
from incidents.models import DistillationRun, Incident, Subject, TriageLesson
from incidents.services.transitions import transition_incident
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


@pytest.fixture
def human(db, django_user_model):
    return django_user_model.objects.create_user(username="analyst", password="p", is_staff=True)


class FakeDistiller:
    def __init__(self, guidance="verify the source is not our scanner"):
        self.guidance = guidance
        self.calls = 0

    def distill_triage_lesson(self, payload):
        self.calls += 1
        return {"guidance": self.guidance, "selector": "internal source ip"}


def make_closed(org, subject, *, actor, source_kind="wazuh_event"):
    n = Incident.objects.count()
    inc = Incident.objects.create(organization=org, title=f"Brute force {n}",
                                  description="failed logins", display_id=f"INC-2026-{n + 1:04d}",
                                  subject=subject, source_kind=source_kind, state="new")
    transition_incident(inc, "closed", actor=actor, closure_reason="resolved")
    return inc


@pytest.mark.django_db
def test_run_records_a_proposed_cluster(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    run = run_and_record_sweep(provider=FakeDistiller())

    assert run.eligible_count == 3
    assert run.proposed_count == 1
    assert run.proposed_global_count == 0
    assert run.finished_at is not None
    outcomes = [c["outcome"] for c in run.clusters]
    assert DistillationRun.OUTCOME_PROPOSED in outcomes
    proposed_cluster = next(c for c in run.clusters if c["outcome"] == "proposed")
    assert proposed_cluster["tier"] == "org"
    assert proposed_cluster["organization"] == "acme"
    assert proposed_cluster["subject"] == brute.name
    assert proposed_cluster["evidence_count"] == 3
    # LLM I/O is captured for troubleshooting: the prompt handed to the distiller and its
    # raw response (#697).
    assert proposed_cluster["prompt"]["subject"] == brute.name
    assert len(proposed_cluster["prompt"]["incidents"]) == 3
    assert proposed_cluster["response"]["guidance"] == "verify the source is not our scanner"


class BoomDistiller:
    """Raises for every cluster — stands in for a distiller/LLM failure."""
    def distill_triage_lesson(self, payload):
        raise RuntimeError("model timeout")


@pytest.mark.django_db
def test_distiller_error_is_recorded_with_prompt_and_message(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    run = run_and_record_sweep(provider=BoomDistiller())

    assert run.proposed_count == 0
    cluster = run.clusters[0]
    assert cluster["outcome"] == DistillationRun.OUTCOME_DISTILLER_ERROR
    assert cluster["error"] == "model timeout"
    # The prompt is retained so the failing call can be reproduced; there is no response.
    assert cluster["prompt"]["subject"] == brute.name
    assert "response" not in cluster


@pytest.mark.django_db
def test_skipped_clusters_carry_no_llm_io(acme, brute, human):
    # Two cases → below threshold → distiller never runs → no prompt/response/error stored.
    make_closed(acme, brute, actor=human)
    make_closed(acme, brute, actor=human)
    run = run_and_record_sweep(provider=FakeDistiller())

    cluster = run.clusters[0]
    assert cluster["outcome"] == DistillationRun.OUTCOME_INSUFFICIENT_EVIDENCE
    assert "prompt" not in cluster and "response" not in cluster and "error" not in cluster


@pytest.mark.django_db
def test_zero_proposal_run_still_records_why(acme, brute, human):
    # Only 2 incidents: below the evidence threshold, so nothing is proposed — but the run
    # must still record that it looked and why it skipped.
    make_closed(acme, brute, actor=human)
    make_closed(acme, brute, actor=human)
    run = run_and_record_sweep(provider=FakeDistiller())

    assert run.proposed_count == 0
    assert run.cluster_count == 1
    assert run.clusters[0]["outcome"] == DistillationRun.OUTCOME_INSUFFICIENT_EVIDENCE
    assert run.clusters[0]["evidence_count"] == 2


@pytest.mark.django_db
def test_covering_lesson_recorded_as_skip(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    run_and_record_sweep(provider=FakeDistiller())      # first run proposes → covering lesson
    run = run_and_record_sweep(provider=FakeDistiller())  # second run should skip it

    assert run.proposed_count == 0
    assert run.clusters[0]["outcome"] == DistillationRun.OUTCOME_COVERING_LESSON


@pytest.mark.django_db
def test_runs_are_pruned_to_retention(acme, brute, human):
    make_closed(acme, brute, actor=human)  # 1 eligible incident, nothing proposed
    for _ in range(RUN_RETENTION + 5):
        run_and_record_sweep(provider=FakeDistiller())
    assert DistillationRun.objects.count() == RUN_RETENTION


@pytest.mark.django_db
def test_runs_endpoint_is_staff_only(acme, brute, human, django_user_model):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    run_and_record_sweep(provider=FakeDistiller())

    client = APIClient()

    # Anonymous / non-staff is denied.
    tenant = django_user_model.objects.create_user(username="t", password="p")
    client.force_authenticate(tenant)
    assert client.get("/api/incidents/triage-lessons/runs/").status_code == 403

    # Staff sees the run summary with its per-cluster breakdown.
    client.force_authenticate(human)
    resp = client.get("/api/incidents/triage-lessons/runs/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["proposed_count"] == 1
    assert resp.data[0]["clusters"][0]["outcome"] == "proposed"
