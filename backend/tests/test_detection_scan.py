"""Tests for the Detection Scan (PRD #727, ADR-0036).

Covers the Candidate Neighbourhood assembler (pure DB + clock) and the Scan
orchestrator with a stubbed LLM — external behaviour only: resulting
DetectionSuggestion rows, never which helper ran.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

from alerts.models import Alert, AlertEntity
from correlations.models import DetectionSuggestion
from correlations.services.neighbourhoods import (
    LOOKBACK_HOURS,
    NEIGHBOURHOOD_SIZE_CAP,
    SETTLE_MINUTES,
    assemble_neighbourhoods,
)
from correlations.tasks import _run_scan_for_org
from incidents.llm.base import ResidualGroup, ResidualGroupingResult, TriageConfigError
from incidents.models import Incident
from security.models import Organization


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="ScanTest", slug="scantest", wazuh_group="scantest"
    )


@pytest.fixture
def other_org(db):
    return Organization.objects.create(
        name="ScanOther", slug="scanother", wazuh_group="scanother"
    )


_SETTLED_AGE = SETTLE_MINUTES + 10


def _make_alert(org, state="new", incident=None, age_minutes=_SETTLED_AGE,
                severity="medium", entities=()):
    count = Alert.objects.count()
    a = Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind="wazuh_event",
        source_ref={"rule_id": "9999"},
        title="Test alert",
        severity=severity,
        state=state,
        incident=incident,
    )
    if age_minutes is not None:
        Alert.objects.filter(pk=a.pk).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        a.refresh_from_db()
    for entity_type, value in entities:
        AlertEntity.objects.create(
            alert=a, organization=org, entity_type=entity_type, value=value
        )
    return a


def _make_incident(org):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org, display_id=f"INC-{count + 1:04d}", title="existing",
        source_kind="wazuh_event", source_ref={}, state="new", severity="medium",
    )


def _neighbourhood_id_sets(neighbourhoods):
    return [
        (
            {a.id for a in n.residual_alerts},
            {a.id for a in n.context_alerts},
        )
        for n in neighbourhoods
    ]


# ── Candidate Neighbourhood assembler ────────────────────────────────────────

def test_assembler_cross_tenant_isolation(db, org, other_org):
    """Two orgs sharing a common entity value must never co-occur in a neighbourhood."""
    mine1 = _make_alert(org, entities=[("user.name", "administrator")])
    mine2 = _make_alert(org, entities=[("user.name", "administrator")])
    theirs = _make_alert(other_org, entities=[("user.name", "administrator")])

    neighbourhoods = assemble_neighbourhoods(org)

    assert len(neighbourhoods) == 1
    all_ids = {a.id for a in neighbourhoods[0].alerts}
    assert all_ids == {mine1.id, mine2.id}
    assert theirs.id not in all_ids

    # And the other direction: the other org sees only its own (singleton → dropped).
    assert assemble_neighbourhoods(other_org) == []


def test_assembler_union_sharing(db, org):
    """Alerts sharing ANY entity value with the anchor are neighboured (v1 union)."""
    anchor = _make_alert(
        org, age_minutes=120,
        entities=[("host.name", "web-01"), ("user.name", "svc-deploy")],
    )
    via_host = _make_alert(org, age_minutes=100, entities=[("host.name", "web-01")])
    via_user = _make_alert(org, age_minutes=90, entities=[("user.name", "svc-deploy")])
    unrelated = _make_alert(org, age_minutes=80, entities=[("host.name", "db-09")])

    neighbourhoods = assemble_neighbourhoods(org)
    sets = _neighbourhood_id_sets(neighbourhoods)

    assert ({anchor.id, via_host.id, via_user.id}, set()) in sets
    # The unrelated alert forms no ≥2 neighbourhood of its own.
    assert all(unrelated.id not in residual | context for residual, context in sets)


def test_assembler_residual_handled_split(db, org):
    """Handled and unsettled alerts land in context; only settled new/unlinked are residual."""
    inc = _make_incident(org)
    residual = _make_alert(org, entities=[("host.name", "web-01")])
    handled = _make_alert(
        org, state="imported", incident=inc, entities=[("host.name", "web-01")]
    )
    fresh = _make_alert(
        org, age_minutes=SETTLE_MINUTES - 5, entities=[("host.name", "web-01")]
    )

    neighbourhoods = assemble_neighbourhoods(org)

    assert len(neighbourhoods) == 1
    residual_ids = {a.id for a in neighbourhoods[0].residual_alerts}
    context_ids = {a.id for a in neighbourhoods[0].context_alerts}
    assert residual_ids == {residual.id}
    assert context_ids == {handled.id, fresh.id}


def test_assembler_window_boundary(db, org):
    """Alerts outside the lookback window neither anchor nor join a neighbourhood."""
    recent1 = _make_alert(org, entities=[("host.name", "web-01")])
    recent2 = _make_alert(org, entities=[("host.name", "web-01")])
    ancient = _make_alert(
        org, age_minutes=LOOKBACK_HOURS * 60 + 30, entities=[("host.name", "web-01")]
    )

    neighbourhoods = assemble_neighbourhoods(org)

    assert len(neighbourhoods) == 1
    all_ids = {a.id for a in neighbourhoods[0].alerts}
    assert all_ids == {recent1.id, recent2.id}
    assert ancient.id not in all_ids


def test_assembler_size_cap(db, org):
    """A noisy shared entity cannot balloon a neighbourhood past the hard cap."""
    for _ in range(NEIGHBOURHOOD_SIZE_CAP + 5):
        _make_alert(org, entities=[("host.name", "noisy-host")])

    neighbourhoods = assemble_neighbourhoods(org)

    assert neighbourhoods
    for n in neighbourhoods:
        assert len(n.alerts) <= NEIGHBOURHOOD_SIZE_CAP


def test_assembler_singleton_dropped(db, org):
    """An alert sharing no entity with anything yields no neighbourhood."""
    _make_alert(org, entities=[("host.name", "lonely-host")])
    assert assemble_neighbourhoods(org) == []


# ── Scan orchestrator (stubbed LLM) ──────────────────────────────────────────

def _stub_provider(groups):
    provider = MagicMock()
    provider.scan_neighbourhood.return_value = ResidualGroupingResult(
        groups=groups, provider="stub"
    )
    return provider


def _run_with(provider, org):
    with patch("incidents.llm.factory.get_triage_provider", return_value=provider):
        _run_scan_for_org(org)


def test_scan_valid_group_creates_suggestion(db, org):
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="same-host cluster", confidence=0.8)]
    )
    _run_with(provider, org)

    suggestion = DetectionSuggestion.objects.get(organization=org)
    assert suggestion.status == DetectionSuggestion.STATUS_PENDING
    assert suggestion.confidence == 0.8
    assert set(suggestion.proposed_alerts.values_list("id", flat=True)) == {a1.id, a2.id}


def test_scan_group_may_span_residual_and_handled(db, org):
    """A mixed group (≥1 residual + handled context) is a valid proposal."""
    inc = _make_incident(org)
    residual = _make_alert(org, entities=[("host.name", "web-01")])
    handled = _make_alert(
        org, state="imported", incident=inc, entities=[("host.name", "web-01")]
    )

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[residual.id, handled.id], rationale="one attack", confidence=0.9)]
    )
    _run_with(provider, org)

    suggestion = DetectionSuggestion.objects.get(organization=org)
    assert set(suggestion.proposed_alerts.values_list("id", flat=True)) == {
        residual.id,
        handled.id,
    }


def test_scan_residual_context_distinction_reaches_provider(db, org):
    """The provider receives residual and context payloads separately."""
    inc = _make_incident(org)
    residual = _make_alert(org, entities=[("host.name", "web-01")])
    handled = _make_alert(
        org, state="imported", incident=inc, entities=[("host.name", "web-01")]
    )

    provider = _stub_provider([])
    _run_with(provider, org)

    (residual_payloads, context_payloads), _ = provider.scan_neighbourhood.call_args
    assert [p["id"] for p in residual_payloads] == [residual.id]
    assert [p["id"] for p in context_payloads] == [handled.id]
    assert all("entities" in p for p in residual_payloads + context_payloads)


def test_scan_below_confidence_dropped(db, org):
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="weak", confidence=0.3)]
    )
    _run_with(provider, org)

    assert DetectionSuggestion.objects.filter(organization=org).count() == 0


def test_scan_all_handled_group_suppressed(db, org):
    """A group with no residual alert is a duplicate of an existing incident."""
    inc = _make_incident(org)
    _make_alert(org, entities=[("host.name", "web-01")])  # residual anchor
    h1 = _make_alert(org, state="imported", incident=inc, entities=[("host.name", "web-01")])
    h2 = _make_alert(org, state="imported", incident=inc, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[h1.id, h2.id], rationale="already handled", confidence=0.9)]
    )
    _run_with(provider, org)

    assert DetectionSuggestion.objects.filter(organization=org).count() == 0


def test_scan_singleton_group_dropped(db, org):
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, 999999], rationale="unknown id", confidence=0.9)]
    )
    _run_with(provider, org)

    assert DetectionSuggestion.objects.filter(organization=org).count() == 0


def test_scan_rerun_does_not_duplicate(db, org):
    """A second run over the same window does not duplicate the pending suggestion."""
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="same-host cluster", confidence=0.8)]
    )
    _run_with(provider, org)
    _run_with(provider, org)

    assert DetectionSuggestion.objects.filter(organization=org).count() == 1


def test_scan_unconfigured_provider_skips_org(db, org):
    _make_alert(org, entities=[("host.name", "web-01")])
    _make_alert(org, entities=[("host.name", "web-01")])

    with patch(
        "incidents.llm.factory.get_triage_provider",
        side_effect=TriageConfigError("not configured"),
    ):
        _run_scan_for_org(org)  # must not raise

    assert DetectionSuggestion.objects.filter(organization=org).count() == 0


# ── auto-create threshold (retained from the safety-net, default off) ────────

def test_scan_autocreate_off_by_default(db, org):
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="cluster", confidence=0.95)]
    )
    _run_with(provider, org)

    s = DetectionSuggestion.objects.get(organization=org)
    assert s.status == DetectionSuggestion.STATUS_PENDING
    assert s.incident is None


def test_scan_autocreate_fires_when_threshold_met(db, org):
    org.llm_residual_autocreate_threshold = 0.8
    org.save()

    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="attack cluster", confidence=0.85)]
    )
    with patch("incidents.tasks.enrich_iocs_then_triage") as mock_enrich:
        mock_enrich.delay = MagicMock()
        _run_with(provider, org)

    s = DetectionSuggestion.objects.get(organization=org)
    assert s.status == DetectionSuggestion.STATUS_ACCEPTED
    assert s.incident is not None


def test_scan_autocreate_skipped_below_threshold(db, org):
    org.llm_residual_autocreate_threshold = 0.9
    org.save()

    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="borderline", confidence=0.85)]
    )
    _run_with(provider, org)

    s = DetectionSuggestion.objects.get(organization=org)
    assert s.status == DetectionSuggestion.STATUS_PENDING
    assert s.incident is None


# ── Suggestion reconciler (dedup ledger, #729) ───────────────────────────────

from correlations.services.suggestion_reconciler import (  # noqa: E402
    ACTION_CREATE,
    ACTION_FOLD,
    ACTION_SUPPRESS,
    reconcile,
)
from correlations.tasks import _create_incident_from_suggestion  # noqa: E402


def _make_suggestion(org, alerts, status=DetectionSuggestion.STATUS_PENDING):
    s = DetectionSuggestion.objects.create(
        organization=org, rationale="prior grouping", confidence=0.7, status=status
    )
    s.proposed_alerts.set(alerts)
    return s


def test_reconcile_creates_when_no_overlap(db, org):
    a1, a2 = _make_alert(org), _make_alert(org)
    _make_suggestion(org, [_make_alert(org), _make_alert(org)])

    decision = reconcile(org, {a1.id, a2.id})
    assert decision.action == ACTION_CREATE


def test_reconcile_suppresses_same_set_as_pending(db, org):
    a1, a2 = _make_alert(org), _make_alert(org)
    _make_suggestion(org, [a1, a2])

    decision = reconcile(org, {a1.id, a2.id})
    assert decision.action == ACTION_SUPPRESS


def test_reconcile_folds_overlapping_into_pending(db, org):
    a1, a2, a3 = _make_alert(org), _make_alert(org), _make_alert(org)
    live = _make_suggestion(org, [a1, a2])

    decision = reconcile(org, {a1.id, a2.id, a3.id})
    assert decision.action == ACTION_FOLD
    assert decision.suggestion.id == live.id


def test_reconcile_dismissed_same_set_suppresses(db, org):
    a1, a2 = _make_alert(org), _make_alert(org)
    _make_suggestion(org, [a1, a2], status=DetectionSuggestion.STATUS_DISMISSED)

    decision = reconcile(org, {a1.id, a2.id})
    assert decision.action == ACTION_SUPPRESS


def test_reconcile_dismissed_subset_suppresses(db, org):
    a1, a2, a3 = _make_alert(org), _make_alert(org), _make_alert(org)
    _make_suggestion(org, [a1, a2, a3], status=DetectionSuggestion.STATUS_DISMISSED)

    decision = reconcile(org, {a1.id, a2.id})
    assert decision.action == ACTION_SUPPRESS


def test_reconcile_dismissed_one_new_alert_still_suppresses(db, org):
    """One stray extra alert is not material new evidence."""
    a1, a2, a3 = _make_alert(org), _make_alert(org), _make_alert(org)
    _make_suggestion(org, [a1, a2], status=DetectionSuggestion.STATUS_DISMISSED)

    decision = reconcile(org, {a1.id, a2.id, a3.id})
    assert decision.action == ACTION_SUPPRESS


def test_reconcile_dismissed_materially_larger_reproposes(db, org):
    a1, a2, a3, a4 = (_make_alert(org) for _ in range(4))
    _make_suggestion(org, [a1, a2], status=DetectionSuggestion.STATUS_DISMISSED)

    decision = reconcile(org, {a1.id, a2.id, a3.id, a4.id})
    assert decision.action == ACTION_CREATE


def test_scan_folds_new_evidence_into_live_suggestion(db, org):
    """Orchestrator + reconciler: a grown grouping updates the pending row in place."""
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="pair", confidence=0.7)]
    )
    _run_with(provider, org)

    a3 = _make_alert(org, entities=[("host.name", "web-01")])
    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id, a3.id], rationale="trio", confidence=0.8)]
    )
    _run_with(provider, org)

    suggestion = DetectionSuggestion.objects.get(organization=org)
    assert suggestion.status == DetectionSuggestion.STATUS_PENDING
    assert set(suggestion.proposed_alerts.values_list("id", flat=True)) == {
        a1.id, a2.id, a3.id,
    }
    assert suggestion.confidence == 0.8


def test_scan_dismissed_grouping_stays_dismissed(db, org):
    """Orchestrator + reconciler: a dismissed grouping does not come back."""
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])
    _make_suggestion(org, [a1, a2], status=DetectionSuggestion.STATUS_DISMISSED)

    provider = _stub_provider(
        [ResidualGroup(alert_ids=[a1.id, a2.id], rationale="again", confidence=0.9)]
    )
    _run_with(provider, org)

    assert (
        DetectionSuggestion.objects.filter(
            organization=org, status=DetectionSuggestion.STATUS_PENDING
        ).count()
        == 0
    )


def test_accepted_alerts_leave_residual_pool(db, org):
    """Accepting moves alerts to imported, removing them from Residual candidacy."""
    a1 = _make_alert(org, entities=[("host.name", "web-01")])
    a2 = _make_alert(org, entities=[("host.name", "web-01")])
    suggestion = _make_suggestion(org, [a1, a2])

    with patch("incidents.tasks.enrich_iocs_then_triage") as mock_enrich:
        mock_enrich.delay = MagicMock()
        _create_incident_from_suggestion(suggestion)

    a1.refresh_from_db()
    assert a1.state == "imported"
    # No residual anchor remains, so no neighbourhood is assembled at all.
    assert assemble_neighbourhoods(org) == []
