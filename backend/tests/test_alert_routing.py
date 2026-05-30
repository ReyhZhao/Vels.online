import pytest
from security.models import Organization
from alerts.models import Alert
from alerts.services.routing import route_alert
from incidents.models import Incident, IncidentEvent


@pytest.fixture
def acme(db):
    return Organization.objects.create(
        name="Acme", slug="acme", wazuh_group="acme",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _make_alert(org, severity="medium", source_kind="wazuh_event", source_ref=None, state="new", **kwargs):
    count = Alert.objects.count()
    return Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind=source_kind,
        source_ref=source_ref or {"rule_id": "100002", "rule_description": "Test rule", "agent_name": "web-01"},
        title=None,
        severity=severity,
        state=state,
        **kwargs,
    )


def _make_incident(org, source_kind="wazuh_event", source_ref=None, state="new"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        display_id=f"INC-2026-{count + 1:04d}",
        title="Test incident",
        source_kind=source_kind,
        source_ref=source_ref or {},
        state=state,
    )


# ── Auto-link (matching existing incident) ───────────────────────────────────


def test_route_links_to_matching_incident(acme):
    inc = _make_incident(acme, source_ref={"rule_id": "100002", "rule_description": "Test rule"})
    alert = _make_alert(acme, severity="medium")

    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "imported"
    assert alert.incident_id == inc.id


def test_route_match_takes_precedence_over_high_severity(acme):
    inc = _make_incident(acme, source_ref={"rule_id": "100002"})
    alert = _make_alert(acme, severity="high")  # would normally promote, but match wins

    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "imported"
    assert alert.incident_id == inc.id
    # Should not have created a new incident
    assert Incident.objects.count() == 1


def test_route_match_creates_timeline_event(acme):
    inc = _make_incident(acme, source_ref={"rule_id": "100002"})
    alert = _make_alert(acme, severity="medium")

    route_alert(alert)

    events = IncidentEvent.objects.filter(incident=inc, kind="alert_linked")
    assert events.exists()
    assert events.first().payload["alert_display_id"] == alert.display_id


# ── Auto-promote high/critical ───────────────────────────────────────────────


def test_route_high_no_match_creates_incident(acme):
    alert = _make_alert(acme, severity="high")
    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "imported"
    assert alert.incident is not None
    assert Incident.objects.count() == 1


def test_route_critical_no_match_creates_incident(acme):
    alert = _make_alert(acme, severity="critical")
    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "imported"
    assert alert.incident is not None


def test_route_medium_no_match_stays_new(acme):
    alert = _make_alert(acme, severity="medium", source_ref={"rule_id": "unique-99999"})
    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "new"
    assert alert.incident is None
    assert Incident.objects.count() == 0


def test_route_low_no_match_stays_new(acme):
    alert = _make_alert(acme, severity="low", source_ref={"rule_id": "unique-99998"})
    route_alert(alert)
    alert.refresh_from_db()

    assert alert.state == "new"
    assert alert.incident is None


def test_auto_promoted_incident_has_correct_fields(acme):
    source_ref = {"rule_id": "888", "rule_description": "Brute force", "agent_name": "db-01", "level": 12}
    alert = _make_alert(acme, severity="critical", source_ref=source_ref)

    route_alert(alert)
    alert.refresh_from_db()

    inc = alert.incident
    assert inc.source_kind == "wazuh_event"
    assert inc.display_id.startswith("INC-")
    assert "db-01" in inc.title


# ── Side effects ──────────────────────────────────────────────────────────────


def test_route_bumps_incident_severity(acme):
    inc = _make_incident(acme, source_ref={"rule_id": "100002"})
    inc.severity = "medium"
    inc.save()
    alert = _make_alert(acme, severity="critical")

    route_alert(alert)

    inc.refresh_from_db()
    assert inc.severity == "critical"


def test_route_does_not_lower_incident_severity(acme):
    inc = _make_incident(acme, source_ref={"rule_id": "100002"})
    inc.severity = "critical"
    inc.save()
    alert = _make_alert(acme, severity="low")

    route_alert(alert)

    inc.refresh_from_db()
    assert inc.severity == "critical"


# ── Explicit alert fields override auto-derived (#326) ─────────────���─────────


def _make_workflow_alert(org, **kwargs):
    count = Alert.objects.count()
    defaults = dict(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind="workflow",
        source_ref={},
        title="Workflow alert",
        severity="high",
        state="new",
    )
    defaults.update(kwargs)
    return Alert.objects.create(**defaults)


def test_explicit_description_used_in_promoted_incident(acme):
    alert = _make_workflow_alert(acme, description="N8N crafted this description.")
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.description == "N8N crafted this description."


def test_null_description_falls_back_to_auto_derived(acme):
    source_ref = {"rule_id": "X", "rule_description": "Brute force", "agent_name": "web-01", "level": 9}
    count = Alert.objects.count()
    alert = Alert.objects.create(
        organization=acme,
        display_id=f"AL-{count + 1:04d}",
        source_kind="wazuh_event",
        source_ref=source_ref,
        title="Test",
        severity="high",
        description=None,
        state="new",
    )
    route_alert(alert)
    alert.refresh_from_db()
    # Auto-derived description for wazuh_event includes the rule and agent
    assert "Brute force" in alert.incident.description
    assert "web-01" in alert.incident.description


def test_explicit_severity_overrides_auto_derived(acme):
    alert = _make_workflow_alert(acme, severity="critical")
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.severity == "critical"


def test_explicit_pap_propagates_to_incident(acme):
    alert = _make_workflow_alert(acme, pap="red")
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.pap == "red"


def test_null_pap_incident_gets_amber_default(acme):
    alert = _make_workflow_alert(acme, pap=None)
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.pap == "amber"


def test_explicit_tlp_propagates_to_incident(acme):
    alert = _make_workflow_alert(acme, tlp="green")
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.tlp == "green"


def test_null_tlp_incident_gets_amber_default(acme):
    alert = _make_workflow_alert(acme, tlp=None)
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.tlp == "amber"


def test_explicit_title_used_in_promoted_incident(acme):
    alert = _make_workflow_alert(acme, title="Explicit workflow title")
    route_alert(alert)
    alert.refresh_from_db()
    assert alert.incident.title == "Explicit workflow title"


def test_deduplication_does_not_overwrite_incident_fields(acme):
    """Linking an enriched alert to an existing incident must not modify the incident's fields."""
    inc = _make_incident(acme, source_ref={"rule_id": "100002"})
    inc.pap = "white"
    inc.tlp = "red"
    inc.description = "Original analyst description."
    inc.save()

    alert = _make_workflow_alert(
        acme,
        source_ref={"rule_id": "100002"},
        pap="amber",
        tlp="green",
        description="N8N description that should NOT overwrite.",
    )
    route_alert(alert)

    inc.refresh_from_db()
    assert inc.pap == "white"
    assert inc.tlp == "red"
    assert inc.description == "Original analyst description."
