"""Retrospective measurement for issue #657 — would semantic (embedding) precedent
retrieval recover Precedents the entity/keyword `Q` misses?

Correction-anchored, strictly per-org (ADR-0030/0031). These tests exercise the pure
measurement logic with a deterministic bag-of-words fake embedder — no provider, no store.
"""
from collections import Counter
from datetime import timedelta

import pytest

from incidents.memory import semantic_measure as sm
from incidents.models import (
    Asset,
    ClassificationCorrection,
    IncidentAsset,
    IOC,
    Incident,
    Subject,
)
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def globex(db):
    return Organization.objects.create(name="Globex", slug="globex", wazuh_group="globex")


def make_incident(org, *, title="Suspicious login", description="failed ssh from host",
                  state="new", subject=None, closure_reason=None):
    n = Incident.objects.count()
    return Incident.objects.create(
        organization=org, title=title, description=description,
        display_id=f"INC-2026-{n + 1:04d}", state=state,
        subject=subject, closure_reason=closure_reason,
    )


def close_before(incident, query):
    """Force `incident` to look concluded strictly before `query` was created."""
    Incident.objects.filter(pk=incident.pk).update(
        updated_at=query.created_at - timedelta(seconds=1)
    )


def add_ioc(incident, value, kind="ip"):
    return IOC.objects.create(incident=incident, kind=kind, value=value)


def link_asset(incident, org, agent_name="web-01", ip="10.0.0.9"):
    asset = Asset.objects.create(organization=org, kind="host", name=agent_name,
                                 agent_name=agent_name, ip_address=ip)
    IncidentAsset.objects.create(incident=incident, asset=asset)


def correct_to(incident, subject):
    return ClassificationCorrection.objects.create(incident=incident, human_subject=subject)


def bow_embedder(texts):
    """Deterministic bag-of-words embedder: cosine ≈ shared-token overlap."""
    vocab = sorted({tok for text in texts for tok in text.lower().split()})
    return [[float(text.lower().split().count(w)) for w in vocab] for text in texts]


def exploding_embedder(texts):  # asserts the embedder is *not* called
    raise AssertionError("embedder must not be called when keyword retrieval covers the case")


# ── primitives ──────────────────────────────────────────────────────────────────


def test_cosine_identical_orthogonal_and_zero():
    assert sm.cosine([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)
    assert sm.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert sm.cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


@pytest.mark.django_db
def test_embedding_text_includes_title_description_and_entities(acme):
    inc = make_incident(acme, title="Brute force", description="many failures")
    add_ioc(inc, "1.2.3.4")
    link_asset(inc, acme, agent_name="db-01", ip="10.0.0.50")
    text = sm.embedding_text(inc)
    for token in ("Brute force", "many failures", "1.2.3.4", "db-01", "10.0.0.50"):
        assert token in text


# ── corpus reconstruction (isolation + time bound) ───────────────────────────────


@pytest.mark.django_db
def test_corpus_is_per_org_only(acme, globex):
    query = make_incident(acme)
    foreign = make_incident(globex, state="closed", closure_reason="resolved")
    close_before(foreign, query)
    assert list(sm.corpus_for(query)) == []


@pytest.mark.django_db
def test_corpus_excludes_incidents_concluded_after_the_query(acme):
    query = make_incident(acme)
    later = make_incident(acme, state="closed", closure_reason="resolved")  # updated_at now > query
    assert later not in list(sm.corpus_for(query))


@pytest.mark.django_db
def test_corpus_excludes_still_open_incidents(acme):
    query = make_incident(acme)
    open_inc = make_incident(acme, state="in_progress")
    close_before(open_inc, query)
    assert open_inc not in list(sm.corpus_for(query))


# ── the four buckets ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_keyword_covered_does_not_call_the_embedder(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    query = make_incident(acme)
    add_ioc(query, "1.2.3.4")
    prior = make_incident(acme, state="closed", closure_reason="resolved", subject=subj)
    add_ioc(prior, "1.2.3.4")  # shared IOC → keyword finds it
    close_before(prior, query)

    outcome = sm.classify_correction(correct_to(query, subj), exploding_embedder)
    assert outcome.bucket == sm.KEYWORD_COVERED
    assert prior.pk in outcome.keyword_ids


@pytest.mark.django_db
def test_embedding_recovers_a_prior_keyword_missed(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    query = make_incident(acme, title="repeated failed login", description="ssh brute force burst")
    add_ioc(query, "1.2.3.4")
    # Right subject, NO shared entity (keyword misses) but near-identical text (embedding hits).
    prior = make_incident(acme, title="repeated failed login", description="ssh brute force burst",
                          state="closed", closure_reason="resolved", subject=subj)
    add_ioc(prior, "9.9.9.9")
    close_before(prior, query)

    outcome = sm.classify_correction(correct_to(query, subj), bow_embedder)
    assert outcome.bucket == sm.EMBEDDING_RECOVERED
    assert prior.pk not in outcome.keyword_ids
    assert prior.pk in outcome.embedding_ids


@pytest.mark.django_db
def test_both_missed_when_prior_exists_but_neither_ranks_it(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    query = make_incident(acme, title="alpha", description="alpha alpha", state="new")
    add_ioc(query, "1.2.3.4")
    # Right subject but totally dissimilar text and no shared entity.
    prior = make_incident(acme, title="zeta", description="zeta zeta",
                          state="closed", closure_reason="resolved", subject=subj)
    add_ioc(prior, "9.9.9.9")
    close_before(prior, query)
    # top_k decoys that outrank the true prior on the query's own words.
    for i in range(sm.DEFAULT_TOP_K):
        decoy = make_incident(acme, title="alpha", description="alpha alpha",
                              state="closed", closure_reason="resolved")
        add_ioc(decoy, f"5.5.5.{i}")
        close_before(decoy, query)

    outcome = sm.classify_correction(correct_to(query, subj), bow_embedder)
    assert outcome.bucket == sm.BOTH_MISSED
    assert prior.pk not in outcome.embedding_ids


@pytest.mark.django_db
def test_corpus_gap_when_no_prior_has_the_subject(acme):
    subj = Subject.objects.create(name="Brute Force", slug="sem-bf")
    other = Subject.objects.create(name="Other", slug="sem-other")
    query = make_incident(acme)
    add_ioc(query, "1.2.3.4")
    prior = make_incident(acme, state="closed", closure_reason="resolved", subject=other)
    add_ioc(prior, "1.2.3.4")
    close_before(prior, query)

    outcome = sm.classify_correction(correct_to(query, subj), exploding_embedder)
    assert outcome.bucket == sm.CORPUS_GAP


# ── the pre-registered verdict bands ─────────────────────────────────────────────


def _report(counts, *, min_sample=1):
    return sm.MeasurementReport(
        scored=sum(counts.values()), skipped_no_subject=0, buckets=Counter(counts),
        per_org={}, recovered_examples=[], min_sample=min_sample,
        build_threshold=sm.BUILD_THRESHOLD, close_threshold=sm.CLOSE_THRESHOLD,
    )


def test_verdict_build_at_or_above_25pct():
    r = _report({sm.EMBEDDING_RECOVERED: 1, sm.KEYWORD_COVERED: 3})  # 25%
    assert r.headline == pytest.approx(0.25)
    assert r.verdict == sm.VERDICT_BUILD


def test_verdict_close_below_10pct():
    r = _report({sm.EMBEDDING_RECOVERED: 0, sm.KEYWORD_COVERED: 20})  # 0% — keyword suffices
    assert r.headline == 0.0
    assert r.verdict == sm.VERDICT_CLOSE


def test_verdict_inconclusive_between_the_bands():
    r = _report({sm.EMBEDDING_RECOVERED: 1, sm.KEYWORD_COVERED: 5})  # ~16.7%
    assert sm.CLOSE_THRESHOLD <= r.headline < sm.BUILD_THRESHOLD
    assert r.verdict == sm.VERDICT_INCONCLUSIVE


def test_verdict_withheld_below_min_sample_even_at_high_recovery():
    r = _report({sm.EMBEDDING_RECOVERED: 3}, min_sample=20)  # 100% but only 3 cases
    assert r.verdict == sm.VERDICT_INSUFFICIENT


# ── aggregation + verdict ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_measurement_skips_corrections_without_a_human_subject(acme):
    query = make_incident(acme)
    ClassificationCorrection.objects.create(incident=query, human_subject=None,
                                            human_severity="high")
    report = sm.run_measurement(ClassificationCorrection.objects.all(), exploding_embedder)
    assert report.scored == 0
    assert report.skipped_no_subject == 1


@pytest.mark.django_db
def test_run_measurement_withholds_verdict_below_min_sample(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    query = make_incident(acme)
    add_ioc(query, "1.2.3.4")
    prior = make_incident(acme, state="closed", closure_reason="resolved", subject=subj)
    add_ioc(prior, "1.2.3.4")
    close_before(prior, query)
    correct_to(query, subj)

    report = sm.run_measurement(ClassificationCorrection.objects.all(), bow_embedder,
                                min_sample=20)
    assert report.exists_total == 1
    assert report.verdict == sm.VERDICT_INSUFFICIENT


@pytest.mark.django_db
def test_run_measurement_build_verdict_on_high_recovery(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    for i in range(4):
        query = make_incident(acme, title="repeated failed login",
                              description="ssh brute force burst")
        add_ioc(query, f"1.2.3.{i}")
        prior = make_incident(acme, title="repeated failed login",
                              description="ssh brute force burst",
                              state="closed", closure_reason="resolved", subject=subj)
        add_ioc(prior, f"9.9.9.{i}")  # no shared entity → keyword misses, text → embedding hits
        close_before(prior, query)
        correct_to(query, subj)

    report = sm.run_measurement(ClassificationCorrection.objects.all(), bow_embedder,
                                min_sample=3)
    assert report.buckets[sm.EMBEDDING_RECOVERED] == 4
    assert report.headline == pytest.approx(1.0)
    assert report.verdict == sm.VERDICT_BUILD
    assert len(report.recovered_examples) == 4
