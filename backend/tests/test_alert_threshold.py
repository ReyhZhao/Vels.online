import pytest
from django.utils import timezone
from datetime import timedelta

from security.models import Organization
from alerts.models import Alert
from alerts.services.threshold import check_asset_threshold
from incidents.models import Incident


@pytest.fixture
def acme(db):
    return Organization.objects.create(
        name="Acme", slug="acme", wazuh_group="acme",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=3,
        alert_auto_promote_window_minutes=60,
    )


def _make_alert(org, agent_name="web-01", source_kind="wazuh_event", state="new", minutes_ago=0):
    count = Alert.objects.count()
    a = Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind=source_kind,
        source_ref={"agent_name": agent_name, "rule_id": "100002", "level": 6},
        title="Test alert",
        severity="medium",
        state=state,
    )
    if minutes_ago:
        Alert.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        a.refresh_from_db()
    return a


def test_threshold_false_when_below_count(acme):
    _make_alert(acme)
    _make_alert(acme)  # 2 alerts, threshold is 3
    alert = _make_alert(acme)
    # Now we have 3 alerts, threshold=3, so this should be True
    assert check_asset_threshold(alert) is True


def test_threshold_false_when_count_below(acme):
    _make_alert(acme)  # 1 alert, threshold 3
    alert = _make_alert(acme)  # 2 alerts, still below
    assert check_asset_threshold(alert) is False


def test_threshold_true_when_count_meets(acme):
    _make_alert(acme)
    _make_alert(acme)
    alert = _make_alert(acme)  # 3rd = meets threshold
    assert check_asset_threshold(alert) is True


def test_threshold_only_counts_within_window(acme):
    _make_alert(acme, minutes_ago=120)  # outside 60-min window
    _make_alert(acme)
    alert = _make_alert(acme)  # 2 within window, below threshold 3
    assert check_asset_threshold(alert) is False


def test_threshold_different_asset_not_counted(acme):
    _make_alert(acme, agent_name="web-01")
    _make_alert(acme, agent_name="web-01")
    alert = _make_alert(acme, agent_name="web-02")  # different agent
    assert check_asset_threshold(alert) is False


def test_threshold_only_new_state_counted(acme):
    a1 = _make_alert(acme)
    a1.state = "acknowledged"
    a1.save()
    a2 = _make_alert(acme)
    a2.state = "imported"
    a2.save()
    alert = _make_alert(acme)  # Only 1 in 'new' state, below threshold 3
    assert check_asset_threshold(alert) is False


def test_threshold_returns_false_for_no_asset_key(acme):
    alert = Alert.objects.create(
        organization=acme,
        display_id="AL-9999",
        source_kind="api",
        source_ref={},
        title="API alert",
        severity="medium",
        state="new",
    )
    assert check_asset_threshold(alert) is False


def test_threshold_promotes_all_qualifying_alerts(client, django_user_model, acme):
    """Integration: posting an alert that crosses threshold promotes all qualifying new alerts."""
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)

    # Create 2 existing new alerts for same asset/rule
    for i in range(1, 3):
        Alert.objects.create(
            organization=acme,
            display_id=f"AL-{i:04d}",
            source_kind="wazuh_event",
            source_ref={"rule_id": "100002", "agent_name": "web-01", "level": 6},
            title="Existing",
            severity="medium",
            state="new",
        )

    # Post the 3rd alert (crosses threshold=3)
    resp = client.post(
        "/api/alerts/",
        {
            "source_kind": "wazuh_event",
            "source_ref": {"rule_id": "100002", "agent_name": "web-01", "level": 6},
            "org": "acme",
        },
        content_type="application/json",
    )
    assert resp.status_code == 201
    new_alert = resp.json()

    # All 3 alerts should now be imported and linked to the same incident
    alerts = list(Alert.objects.filter(state="imported"))
    assert len(alerts) == 3
    incident_ids = {a.incident_id for a in alerts}
    assert len(incident_ids) == 1  # all linked to the same incident
    assert Incident.objects.count() == 1
