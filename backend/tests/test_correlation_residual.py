"""Tests for DetectionSuggestion parsing, accept transition and API.

The scheduled detector that produces suggestions is the Detection Scan
(PRD #727, ADR-0036) — its assembler/orchestrator tests live in
``test_detection_scan.py``.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

from security.models import Organization, OrganizationMembership
from alerts.models import Alert
from incidents.llm.gemini import _parse_residual_grouping_result
from correlations.models import DetectionSuggestion
from correlations.tasks import (
    _create_incident_from_suggestion,
    _derive_severity,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="ResidualTest",
        slug="residualtest",
        wazuh_group="residualtest",
    )


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member_user(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="pass")


@pytest.fixture
def member(member_user, org):
    OrganizationMembership.objects.create(user=member_user, organization=org)
    return member_user


def _make_alert(org, state="new", incident=None, age_minutes=None, severity="medium"):
    count = Alert.objects.count()
    created_at = timezone.now()
    if age_minutes is not None:
        created_at = timezone.now() - timedelta(minutes=age_minutes)
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
        Alert.objects.filter(pk=a.pk).update(created_at=created_at)
        a.refresh_from_db()
    return a


# ── _parse_residual_grouping_result (unit) ────────────────────────────────────

def test_parse_residual_grouping_result_basic():
    data = {
        "groups": [
            {"alert_ids": [1, 2, 3], "rationale": "Shared host activity", "confidence": 0.8},
            {"alert_ids": [4, 5], "rationale": "Lateral movement pattern", "confidence": 0.65},
        ]
    }
    result = _parse_residual_grouping_result(data)
    assert len(result.groups) == 2
    assert result.groups[0].alert_ids == [1, 2, 3]
    assert result.groups[0].rationale == "Shared host activity"
    assert result.groups[0].confidence == 0.8
    assert result.provider == "gemini"


def test_parse_residual_grouping_result_filters_single_alert():
    """Groups with fewer than 2 alert_ids are discarded."""
    data = {
        "groups": [
            {"alert_ids": [1], "rationale": "Solo alert", "confidence": 0.9},
            {"alert_ids": [2, 3], "rationale": "Pair", "confidence": 0.7},
        ]
    }
    result = _parse_residual_grouping_result(data)
    assert len(result.groups) == 1
    assert result.groups[0].alert_ids == [2, 3]


def test_parse_residual_grouping_result_clamps_confidence():
    data = {"groups": [{"alert_ids": [1, 2], "rationale": "x", "confidence": 1.5}]}
    result = _parse_residual_grouping_result(data)
    assert result.groups[0].confidence == 1.0


def test_parse_residual_grouping_empty():
    assert _parse_residual_grouping_result({"groups": []}).groups == []


# ── _derive_severity (unit) ───────────────────────────────────────────────────

def test_derive_severity_takes_highest(db, org):
    a1 = _make_alert(org, severity="low")
    a2 = _make_alert(org, severity="high")
    a3 = _make_alert(org, severity="medium")
    assert _derive_severity([a1, a2, a3]) == "high"


# ── _create_incident_from_suggestion (accept transition) ─────────────────────

def test_accept_creates_incident_and_links_alerts(db, org):
    a1 = _make_alert(org, state="new", age_minutes=30)
    a2 = _make_alert(org, state="new", age_minutes=30)

    suggestion = DetectionSuggestion.objects.create(
        organization=org,
        rationale="Two alerts sharing the same C2 IP",
        confidence=0.8,
    )
    suggestion.proposed_alerts.set([a1, a2])

    with patch("incidents.tasks.enrich_iocs_then_triage") as mock_enrich:
        mock_enrich.delay = MagicMock()
        incident = _create_incident_from_suggestion(suggestion)

    assert incident is not None
    assert incident.source_kind == "correlation"
    assert incident.organization == org

    suggestion.refresh_from_db()
    assert suggestion.status == DetectionSuggestion.STATUS_ACCEPTED
    assert suggestion.incident == incident

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.state == "imported"
    assert a2.state == "imported"
    assert a1.incident == incident
    assert a2.incident == incident


def test_accept_incident_severity_derived_from_highest_alert(db, org):
    a1 = _make_alert(org, state="new", age_minutes=30, severity="low")
    a2 = _make_alert(org, state="new", age_minutes=30, severity="critical")

    suggestion = DetectionSuggestion.objects.create(
        organization=org, rationale="Mixed severity cluster", confidence=0.7
    )
    suggestion.proposed_alerts.set([a1, a2])

    with patch("incidents.tasks.enrich_iocs_then_triage") as mock_enrich:
        mock_enrich.delay = MagicMock()
        incident = _create_incident_from_suggestion(suggestion)

    assert incident.severity == "critical"


# ── API: list/accept/dismiss (integration) ────────────────────────────────────

@pytest.fixture
def suggestion(db, org):
    a1 = _make_alert(org, state="new", age_minutes=30)
    a2 = _make_alert(org, state="new", age_minutes=30)
    s = DetectionSuggestion.objects.create(
        organization=org, rationale="Suspicious cluster", confidence=0.75
    )
    s.proposed_alerts.set([a1, a2])
    return s


def test_list_suggestions_requires_auth(db, org, client):
    resp = client.get(f"/api/correlations/suggestions/?org={org.slug}")
    assert resp.status_code in (401, 403)


def test_list_suggestions_member(db, org, suggestion, member, client):
    client.force_login(member)
    resp = client.get(f"/api/correlations/suggestions/?org={org.slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == suggestion.id
    assert data[0]["status"] == "pending"


def test_list_suggestions_filters_by_status(db, org, suggestion, member, client):
    client.force_login(member)
    resp = client.get(f"/api/correlations/suggestions/?org={org.slug}&status=accepted")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_dismiss_suggestion(db, org, suggestion, member, client):
    client.force_login(member)
    resp = client.post(f"/api/correlations/suggestions/{suggestion.id}/dismiss/?org={org.slug}")
    assert resp.status_code == 200
    suggestion.refresh_from_db()
    assert suggestion.status == DetectionSuggestion.STATUS_DISMISSED


def test_dismiss_already_dismissed_returns_400(db, org, suggestion, member, client):
    suggestion.status = DetectionSuggestion.STATUS_DISMISSED
    suggestion.save()
    client.force_login(member)
    resp = client.post(f"/api/correlations/suggestions/{suggestion.id}/dismiss/?org={org.slug}")
    assert resp.status_code == 400


def test_accept_suggestion_creates_incident(db, org, suggestion, member, client):
    client.force_login(member)
    with patch("incidents.tasks.enrich_iocs_then_triage") as mock_enrich:
        mock_enrich.delay = MagicMock()
        resp = client.post(f"/api/correlations/suggestions/{suggestion.id}/accept/?org={org.slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_display_id"] is not None

    suggestion.refresh_from_db()
    assert suggestion.status == DetectionSuggestion.STATUS_ACCEPTED
    assert suggestion.incident is not None


def test_accept_suggestion_already_accepted_returns_400(db, org, suggestion, member, client):
    suggestion.status = DetectionSuggestion.STATUS_ACCEPTED
    suggestion.save()
    client.force_login(member)
    resp = client.post(f"/api/correlations/suggestions/{suggestion.id}/accept/?org={org.slug}")
    assert resp.status_code == 400


def test_accept_dismiss_forbidden_for_non_member(db, org, suggestion, django_user_model, client):
    outsider = django_user_model.objects.create_user(username="outsider", password="pass")
    client.force_login(outsider)
    resp = client.post(f"/api/correlations/suggestions/{suggestion.id}/dismiss/?org={org.slug}")
    assert resp.status_code == 403
    resp2 = client.post(f"/api/correlations/suggestions/{suggestion.id}/accept/?org={org.slug}")
    assert resp2 == resp or resp2.status_code == 403
