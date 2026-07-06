"""Distillation sweep — Org-tier proposals (ADR-0030, slice #663).

Eligible signal is strictly human-ratified closures. A scripted distiller stands in for
the LLM so the clustering / N-threshold / dedup / exclusion logic is tested in isolation.
"""
import pytest

from incidents.memory.distillation import run_distillation_sweep
from incidents.models import Incident, Subject, TriageLesson
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
    """Returns a fixed lesson for any cluster; records how many times it was called."""
    def __init__(self, guidance="verify the source is not our scanner"):
        self.guidance = guidance
        self.calls = 0

    def distill_triage_lesson(self, payload):
        self.calls += 1
        return {"guidance": self.guidance, "selector": "internal source ip"}


def make_closed(org, subject, *, actor, closure_reason="resolved", source_kind="wazuh_event"):
    """Create an incident and close it via the real transition (records the closing event)."""
    n = Incident.objects.count()
    inc = Incident.objects.create(organization=org, title=f"Brute force {n}",
                                  description="failed logins", display_id=f"INC-2026-{n + 1:04d}",
                                  subject=subject, source_kind=source_kind, state="new")
    transition_incident(inc, "closed", actor=actor, closure_reason=closure_reason)
    return inc


# ── the N threshold ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_below_threshold_proposes_nothing(acme, brute, human):
    make_closed(acme, brute, actor=human)
    make_closed(acme, brute, actor=human)  # only 2 < N=3
    distiller = FakeDistiller()
    proposed = run_distillation_sweep(provider=distiller)
    assert proposed == []
    assert distiller.calls == 0


@pytest.mark.django_db
def test_at_threshold_proposes_org_lesson(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    distiller = FakeDistiller()
    proposed = run_distillation_sweep(provider=distiller)
    assert len(proposed) == 1
    lesson = proposed[0]
    assert lesson.status == "proposed"
    assert lesson.organization_id == acme.id
    assert lesson.subject_id == brute.id
    assert lesson.provenance == "distilled_from_human_close"
    assert lesson.evidence.count() == 3
    assert "scanner" in lesson.guidance


# ── dedup / idempotency ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_covering_lesson_suppresses_reproposal(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    TriageLesson.objects.create(organization=acme, subject=brute, source_kind="wazuh_event",
                                guidance="already covered", status="active",
                                provenance="staff_authored")
    distiller = FakeDistiller()
    assert run_distillation_sweep(provider=distiller) == []
    assert distiller.calls == 0


@pytest.mark.django_db
def test_sweep_is_idempotent_across_runs(acme, brute, human):
    for _ in range(3):
        make_closed(acme, brute, actor=human)
    distiller = FakeDistiller()
    first = run_distillation_sweep(provider=distiller)
    assert len(first) == 1
    # Second run sees the proposed lesson as covering → proposes nothing more.
    second = run_distillation_sweep(provider=distiller)
    assert second == []


# ── eligible-signal exclusions ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_auto_closed_incidents_are_not_evidence(acme, brute, human):
    # actor=None => machine close (FP auto-close / stale) — excluded.
    for _ in range(3):
        make_closed(acme, brute, actor=None, closure_reason="false_positive")
    assert run_distillation_sweep(provider=FakeDistiller()) == []


@pytest.mark.django_db
def test_duplicate_closures_are_not_evidence(acme, brute, human):
    canonical = make_closed(acme, brute, actor=human)
    for _ in range(3):
        n = Incident.objects.count()
        inc = Incident.objects.create(organization=acme, title="dup", display_id=f"INC-2026-{n + 1:04d}",
                                      subject=brute, source_kind="wazuh_event", state="new")
        transition_incident(inc, "closed", actor=human, closure_reason="duplicate",
                            duplicate_of_id=canonical.id)
    # 3 duplicate closures excluded; only the 1 canonical human close remains < N.
    assert run_distillation_sweep(provider=FakeDistiller()) == []


@pytest.mark.django_db
def test_source_kind_splits_clusters(acme, brute, human):
    for _ in range(2):
        make_closed(acme, brute, actor=human, source_kind="wazuh_event")
    for _ in range(2):
        make_closed(acme, brute, actor=human, source_kind="scheduled_search")
    # 2 + 2, neither cluster reaches N=3.
    assert run_distillation_sweep(provider=FakeDistiller()) == []


# ── Global Lesson promotion (K>=2 orgs) — slice #664 ────────────────────────────


@pytest.fixture
def globex(db):
    return Organization.objects.create(name="Globex", slug="globex", wazuh_group="globex")


class ScopeAwareDistiller:
    """Returns tenant-specific guidance for org clusters and generalised prose for global."""
    def distill_triage_lesson(self, payload):
        if payload.get("scope") == "global":
            return {"guidance": "generalised: treat internal-source brute force as low severity",
                    "selector": "internal source"}
        return {"guidance": "org-specific guidance", "selector": ""}


@pytest.mark.django_db
def test_global_promotion_across_k_orgs(acme, globex, brute, human):
    # 2 in acme + 2 in globex: neither org reaches N=3, but 2 orgs => Global.
    for _ in range(2):
        make_closed(acme, brute, actor=human)
    for _ in range(2):
        make_closed(globex, brute, actor=human)

    proposed = run_distillation_sweep(provider=ScopeAwareDistiller())
    globals_ = [l for l in proposed if l.is_global]
    assert len(globals_) == 1
    g = globals_[0]
    assert g.organization_id is None
    assert g.status == "proposed"
    assert "generalised" in g.guidance
    # evidence spans both tenants (staff-only links)
    assert g.evidence.count() == 4


@pytest.mark.django_db
def test_single_org_does_not_promote_global(acme, brute, human):
    # 2 incidents, one org: below N for org-tier and below K orgs for global.
    for _ in range(2):
        make_closed(acme, brute, actor=human)
    proposed = run_distillation_sweep(provider=ScopeAwareDistiller())
    assert proposed == []


@pytest.mark.django_db
def test_global_covering_lesson_suppresses(acme, globex, brute, human):
    for _ in range(2):
        make_closed(acme, brute, actor=human)
    for _ in range(2):
        make_closed(globex, brute, actor=human)
    TriageLesson.objects.create(organization=None, subject=brute, source_kind="wazuh_event",
                                guidance="already global", status="active",
                                provenance="staff_authored")
    proposed = run_distillation_sweep(provider=ScopeAwareDistiller())
    assert [l for l in proposed if l.is_global] == []
