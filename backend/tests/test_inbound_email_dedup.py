"""Tests for #316: inbound_email dedup matching in find_matching_incident."""
import pytest
from datetime import timedelta

from django.utils import timezone

from alerts.models import Alert
from alerts.services.matching import find_matching_incident
from incidents.models import Incident, IOC
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(
        name="Acme", slug="acme", wazuh_group="acme", alert_match_lookback_days=30
    )


@pytest.fixture
def other_org(db):
    return Organization.objects.create(
        name="Other", slug="other", wazuh_group="other", alert_match_lookback_days=30
    )


def _make_incident(org, source_ref=None, state="new", days_ago=0):
    count = Incident.objects.count()
    inc = Incident.objects.create(
        organization=org,
        display_id=f"INC-2026-{count + 1:04d}",
        title="Phishing",
        source_kind="inbound_email",
        source_ref=source_ref or {},
        state=state,
    )
    if days_ago:
        Incident.objects.filter(pk=inc.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        inc.refresh_from_db()
    return inc


def _make_alert(org, source_ref=None):
    count = Alert.objects.count()
    return Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind="inbound_email",
        source_ref=source_ref or {},
        title="Phishing alert",
        severity="high",
    )


REF = {"sender_address": "phisher@evil.com", "subject_normalised": "win a prize", "forwarder_address": "user@corp.com"}


@pytest.mark.django_db
def test_matches_same_sender_and_subject(acme):
    _make_incident(acme, source_ref=REF)
    alert = _make_alert(acme, source_ref=REF)
    match = find_matching_incident(alert)
    assert match is not None


@pytest.mark.django_db
def test_no_match_when_no_sender_address(acme):
    _make_incident(acme, source_ref=REF)
    alert = _make_alert(acme, source_ref={"subject_normalised": "win a prize"})
    match = find_matching_incident(alert)
    assert match is None


@pytest.mark.django_db
def test_no_match_across_orgs(acme, other_org):
    _make_incident(other_org, source_ref=REF)
    alert = _make_alert(acme, source_ref=REF)
    match = find_matching_incident(alert)
    assert match is None


@pytest.mark.django_db
def test_no_match_closed_incident(acme):
    _make_incident(acme, source_ref=REF, state="closed")
    alert = _make_alert(acme, source_ref=REF)
    match = find_matching_incident(alert)
    assert match is None


@pytest.mark.django_db
def test_no_match_outside_lookback(acme):
    _make_incident(acme, source_ref=REF, days_ago=35)
    alert = _make_alert(acme, source_ref=REF)
    match = find_matching_incident(alert)
    assert match is None


@pytest.mark.django_db
def test_ioc_kind_email_exists():
    assert IOC.KIND_EMAIL == "email"
    assert ("email", "Email Address") in IOC.KIND_CHOICES
