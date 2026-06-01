import pytest
from django.utils import timezone
from datetime import timedelta

from security.models import Organization, OrganizationMembership
from alerts.models import Alert
from alerts.services.matching import find_matching_incident
from incidents.models import Incident


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme",
                                        alert_match_lookback_days=30)


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name="Other", slug="other", wazuh_group="other",
                                        alert_match_lookback_days=30)


def _make_incident(org, source_kind="wazuh_event", source_ref=None, state="new", days_ago=0):
    count = Incident.objects.count()
    inc = Incident.objects.create(
        organization=org,
        display_id=f"INC-2026-{count + 1:04d}",
        title="Test incident",
        source_kind=source_kind,
        source_ref=source_ref or {},
        state=state,
    )
    if days_ago:
        Incident.objects.filter(pk=inc.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        inc.refresh_from_db()
    return inc


def _make_alert(org, source_kind="wazuh_event", source_ref=None):
    count = Alert.objects.count()
    return Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind=source_kind,
        source_ref=source_ref or {},
        title="Test alert",
        severity="medium",
    )


def test_matches_on_rule_id(acme):
    ref = {"rule_id": "100002", "rule_description": "Lateral movement", "agent_name": "web-01"}
    _make_incident(acme, source_ref=ref)
    alert = _make_alert(acme, source_ref={"rule_id": "100002", "agent_name": "web-02"})
    match = find_matching_incident(alert)
    assert match is not None


def test_matches_on_rule_description(acme):
    ref = {"rule_id": "999", "rule_description": "Privilege escalation"}
    _make_incident(acme, source_ref=ref)
    alert = _make_alert(acme, source_ref={"rule_id": "different", "rule_description": "Privilege escalation"})
    match = find_matching_incident(alert)
    assert match is not None


def test_does_not_match_closed_incident(acme):
    ref = {"rule_id": "100002"}
    _make_incident(acme, source_ref=ref, state="closed")
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    match = find_matching_incident(alert)
    assert match is None


def test_does_not_match_outside_lookback(acme):
    ref = {"rule_id": "100002"}
    _make_incident(acme, source_ref=ref, days_ago=35)  # > 30 day lookback
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    match = find_matching_incident(alert)
    assert match is None


def test_does_not_match_different_org(acme, other_org):
    ref = {"rule_id": "100002"}
    _make_incident(other_org, source_ref=ref)
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    match = find_matching_incident(alert)
    assert match is None


def test_returns_most_recent_match(acme):
    ref = {"rule_id": "100002"}
    _make_incident(acme, source_ref=ref, days_ago=10)
    newer = _make_incident(acme, source_ref=ref, days_ago=2)
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    match = find_matching_incident(alert)
    assert match.pk == newer.pk


def test_no_match_when_no_rule_id_or_description(acme):
    _make_incident(acme, source_ref={"agent_name": "web-01"})
    alert = _make_alert(acme, source_ref={"agent_name": "web-01"})
    match = find_matching_incident(alert)
    assert match is None


def test_source_kind_must_match(acme):
    _make_incident(acme, source_kind="vulnerability", source_ref={"rule_id": "100002"})
    alert = _make_alert(acme, source_kind="wazuh_event", source_ref={"rule_id": "100002"})
    match = find_matching_incident(alert)
    assert match is None


@pytest.mark.parametrize("state", ["resolved", "needs_tuning"])
def test_does_not_match_terminal_incident(state, acme):
    ref = {"rule_id": "100002"}
    _make_incident(acme, source_ref=ref, state=state)
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    assert find_matching_incident(alert) is None


@pytest.mark.parametrize("state", ["resolved", "needs_tuning"])
def test_inbound_email_does_not_match_terminal_incident(state, acme):
    ref = {"sender_address": "evil@bad.com", "subject_normalised": "win a prize"}
    _make_incident(acme, source_kind="inbound_email", source_ref=ref, state=state)
    alert = _make_alert(acme, source_kind="inbound_email", source_ref=ref)
    assert find_matching_incident(alert) is None


@pytest.mark.parametrize("state", ["new", "triaged", "in_progress", "on_hold"])
def test_matches_non_terminal_states(state, acme):
    ref = {"rule_id": "100002"}
    _make_incident(acme, source_ref=ref, state=state)
    alert = _make_alert(acme, source_ref={"rule_id": "100002"})
    assert find_matching_incident(alert) is not None
