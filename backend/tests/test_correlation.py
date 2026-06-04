"""Tests for correlation rule leg matching and single-leg rule evaluation."""
import pytest
from security.models import Organization
from alerts.models import Alert, AlertEntity
from datetime import timedelta
from correlations.models import (
    CorrelationRule,
    CorrelationRuleLeg,
    LegCondition,
    FIELD_KIND_ALERT,
    FIELD_KIND_ENTITY,
    FIELD_KIND_SOURCE_REF,
    OPERATOR_EQUALS,
    OPERATOR_IN,
    OPERATOR_CONTAINS,
    OPERATOR_GTE,
    OPERATOR_LTE,
    OPERATOR_CIDR,
)
from correlations.services.matching import alert_matches_leg
from correlations.services.evaluator import evaluate
from incidents.models import Incident


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="CorrelTest",
        slug="correltest",
        wazuh_group="correltest",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _make_alert(org, **kwargs):
    count = Alert.objects.count()
    defaults = dict(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind="wazuh_event",
        source_ref={"rule_id": "9999"},
        title="Test alert",
        severity="medium",
        state="new",
    )
    defaults.update(kwargs)
    return Alert.objects.create(**defaults)


def _add_entity(alert, entity_type, value):
    return AlertEntity.objects.create(
        alert=alert, organization=alert.organization, entity_type=entity_type, value=value
    )


def _make_rule(org=None, correlation_key="none", severity="high"):
    return CorrelationRule.objects.create(
        organization=org,
        name="Test Rule",
        correlation_key=correlation_key,
        window_minutes=60,
        severity=severity,
        enabled=True,
    )


def _make_leg(rule, count=1):
    return CorrelationRuleLeg.objects.create(rule=rule, count=count, display_order=0)


def _make_condition(leg, field_kind, field_name, operator, value):
    return LegCondition.objects.create(
        leg=leg, field_kind=field_kind, field_name=field_name, operator=operator, value=value
    )


# ── alert_matches_leg: alert fields ──────────────────────────────────────────


def test_equals_alert_field_match(org):
    alert = _make_alert(org, severity="high")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "high")
    assert alert_matches_leg(alert, leg) is True


def test_equals_alert_field_no_match(org):
    alert = _make_alert(org, severity="low")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "high")
    assert alert_matches_leg(alert, leg) is False


def test_equals_case_insensitive(org):
    alert = _make_alert(org, title="Port Scan Detected")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_EQUALS, "port scan detected")
    assert alert_matches_leg(alert, leg) is True


def test_in_operator_match(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_IN, '["critical", "high"]')
    assert alert_matches_leg(alert, leg) is True


def test_in_operator_no_match(org):
    alert = _make_alert(org, severity="low")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_IN, '["critical", "high"]')
    assert alert_matches_leg(alert, leg) is False


def test_contains_operator_match(org):
    alert = _make_alert(org, title="Brute force login attempt")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "brute force")
    assert alert_matches_leg(alert, leg) is True


def test_contains_operator_no_match(org):
    alert = _make_alert(org, title="Port scan detected")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "brute force")
    assert alert_matches_leg(alert, leg) is False


def test_gte_operator_match(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_GTE, "high")
    assert alert_matches_leg(alert, leg) is True


def test_gte_operator_equal_boundary(org):
    alert = _make_alert(org, severity="high")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_GTE, "high")
    assert alert_matches_leg(alert, leg) is True


def test_gte_operator_no_match(org):
    alert = _make_alert(org, severity="medium")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_GTE, "high")
    assert alert_matches_leg(alert, leg) is False


def test_lte_operator_match(org):
    alert = _make_alert(org, severity="low")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_LTE, "medium")
    assert alert_matches_leg(alert, leg) is True


def test_lte_operator_no_match(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_LTE, "medium")
    assert alert_matches_leg(alert, leg) is False


# ── alert_matches_leg: entity fields ─────────────────────────────────────────


def test_entity_field_equals_match(org):
    alert = _make_alert(org)
    _add_entity(alert, "source.ip", "10.0.0.5")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ENTITY, "source.ip", OPERATOR_EQUALS, "10.0.0.5")
    assert alert_matches_leg(alert, leg) is True


def test_entity_field_cidr_match(org):
    alert = _make_alert(org)
    _add_entity(alert, "source.ip", "192.168.1.50")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ENTITY, "source.ip", OPERATOR_CIDR, "192.168.1.0/24")
    assert alert_matches_leg(alert, leg) is True


def test_entity_field_cidr_no_match(org):
    alert = _make_alert(org)
    _add_entity(alert, "source.ip", "10.0.0.1")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ENTITY, "source.ip", OPERATOR_CIDR, "192.168.1.0/24")
    assert alert_matches_leg(alert, leg) is False


def test_entity_field_missing_no_match(org):
    alert = _make_alert(org)
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ENTITY, "source.ip", OPERATOR_EQUALS, "10.0.0.1")
    assert alert_matches_leg(alert, leg) is False


# ── alert_matches_leg: source_ref fields ─────────────────────────────────────


def test_source_ref_equals_match(org):
    alert = _make_alert(org, source_ref={"rule_id": "100001", "level": "12"})
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_SOURCE_REF, "rule_id", OPERATOR_EQUALS, "100001")
    assert alert_matches_leg(alert, leg) is True


def test_source_ref_missing_key_no_match(org):
    alert = _make_alert(org, source_ref={})
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_SOURCE_REF, "cve_id", OPERATOR_EQUALS, "CVE-2024-1234")
    assert alert_matches_leg(alert, leg) is False


# ── alert_matches_leg: multiple conditions (AND semantics) ───────────────────


def test_multiple_conditions_all_match(org):
    alert = _make_alert(org, severity="critical", title="Port scan")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    assert alert_matches_leg(alert, leg) is True


def test_multiple_conditions_partial_match_fails(org):
    alert = _make_alert(org, severity="high", title="Port scan")
    rule = _make_rule(org)
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    assert alert_matches_leg(alert, leg) is False


def test_empty_leg_no_match(org):
    alert = _make_alert(org)
    rule = _make_rule(org)
    leg = _make_leg(rule)
    # No conditions added
    assert alert_matches_leg(alert, leg) is False


# ── evaluate: single-leg rule fires incident ─────────────────────────────────


def test_single_leg_rule_creates_incident(org):
    alert = _make_alert(org, severity="high", title="Brute force login")
    rule = _make_rule(org, severity="critical")
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "brute force")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.state == "imported"
    assert alert.incident is not None
    inc = alert.incident
    assert inc.severity == "critical"
    assert inc.source_kind == "correlation"
    assert "Test Rule" in inc.title
    assert "none" in inc.title


def test_single_leg_rule_title_uses_key_value(org):
    alert = _make_alert(org, severity="high")
    _add_entity(alert, "source.ip", "1.2.3.4")
    rule = _make_rule(org, correlation_key="source.ip", severity="high")
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_GTE, "high")

    evaluate(alert)

    alert.refresh_from_db()
    assert "1.2.3.4" in alert.incident.title


def test_disabled_rule_does_not_fire(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org, severity="high")
    rule.enabled = False
    rule.save()
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.incident is None
    assert Incident.objects.count() == 0


def test_rule_for_other_org_does_not_fire(org):
    other_org = Organization.objects.create(
        name="Other",
        slug="other",
        wazuh_group="other",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(other_org, severity="high")
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.incident is None


def test_system_rule_fires_for_any_org(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org=None, severity="high")  # system rule
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.incident is not None
    assert alert.incident.severity == "high"


def test_muted_system_rule_does_not_fire_for_muting_org_but_fires_for_others(org, db):
    from correlations.models import SystemRuleMute

    other_org = Organization.objects.create(
        name="OtherMuteTest",
        slug="othermutetest",
        wazuh_group="othermutetest",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )

    rule = _make_rule(org=None, severity="high")  # system rule
    leg = _make_leg(rule)
    _make_condition(leg, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")

    # Mute the system rule for `org` only
    SystemRuleMute.objects.create(organization=org, rule=rule)

    # Alert from muting org — rule must NOT fire
    alert_muted = _make_alert(org, severity="critical")
    evaluate(alert_muted)
    alert_muted.refresh_from_db()
    assert alert_muted.incident is None

    # Alert from other org — rule must still fire
    alert_other = _make_alert(other_org, severity="critical")
    evaluate(alert_other)
    alert_other.refresh_from_db()
    assert alert_other.incident is not None
    assert alert_other.incident.severity == "high"


# ── evaluate: multi-leg windowed correlation ─────────────────────────────────


def test_two_leg_rule_fires_when_both_legs_satisfied(org):
    alert1 = _make_alert(org, title="port scan detected")
    alert2 = _make_alert(org, title="exploit attempt")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert2)

    alert1.refresh_from_db()
    alert2.refresh_from_db()
    assert alert1.incident is not None
    assert alert2.incident is not None
    assert alert1.incident == alert2.incident
    assert alert1.incident.source_kind == "correlation"


def test_missing_leg_prevents_fire(org):
    alert = _make_alert(org, title="port scan detected")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.incident is None


def test_per_leg_count_requires_enough_alerts(org):
    alert1 = _make_alert(org, title="brute force login")
    alert2 = _make_alert(org, title="brute force login")
    alert3 = _make_alert(org, title="account locked")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=2)  # needs 2 brute force alerts
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "brute force")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "account locked")

    evaluate(alert3)

    alert1.refresh_from_db()
    alert2.refresh_from_db()
    alert3.refresh_from_db()
    assert alert1.incident is not None
    assert alert2.incident is not None
    assert alert3.incident is not None
    assert alert1.incident == alert2.incident == alert3.incident


def test_per_leg_count_insufficient_prevents_fire(org):
    alert1 = _make_alert(org, title="brute force login")
    alert2 = _make_alert(org, title="account locked")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=2)  # needs 2 brute force alerts but only 1 exists
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "brute force")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "account locked")

    evaluate(alert2)

    alert2.refresh_from_db()
    assert alert2.incident is None


def test_correlation_key_isolates_different_entity_values(org):
    alert_host_a1 = _make_alert(org, title="port scan")
    _add_entity(alert_host_a1, "host.name", "host-a")
    alert_host_b = _make_alert(org, title="exploit attempt")
    _add_entity(alert_host_b, "host.name", "host-b")

    rule = _make_rule(org, correlation_key="host.name", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert_host_b)

    alert_host_a1.refresh_from_db()
    alert_host_b.refresh_from_db()
    assert alert_host_b.incident is None  # host-b has no port scan alert


def test_correlation_key_fires_for_matching_entity(org):
    alert1 = _make_alert(org, title="port scan")
    _add_entity(alert1, "host.name", "host-a")
    alert2 = _make_alert(org, title="exploit attempt")
    _add_entity(alert2, "host.name", "host-a")

    rule = _make_rule(org, correlation_key="host.name", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert2)

    alert1.refresh_from_db()
    alert2.refresh_from_db()
    assert alert1.incident is not None
    assert alert2.incident is not None
    assert alert1.incident == alert2.incident
    assert "host-a" in alert1.incident.title


def test_alert_without_required_entity_skips_rule(org):
    alert_no_entity = _make_alert(org, title="port scan")
    # No host.name entity added
    alert_with_entity = _make_alert(org, title="exploit attempt")
    _add_entity(alert_with_entity, "host.name", "host-a")

    rule = _make_rule(org, correlation_key="host.name", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    # Triggering with an alert that lacks host.name — rule is skipped entirely
    evaluate(alert_no_entity)

    alert_no_entity.refresh_from_db()
    assert alert_no_entity.incident is None


def test_window_boundary_excludes_old_alerts(org):
    from django.utils import timezone as tz

    old_alert = _make_alert(org, title="port scan")
    # Backdating: set created_at to outside the window
    Alert.objects.filter(pk=old_alert.pk).update(created_at=tz.now() - timedelta(minutes=120))

    alert2 = _make_alert(org, title="exploit attempt")

    rule = _make_rule(org, correlation_key="none", severity="high")
    rule.window_minutes = 60
    rule.save()
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert2)

    alert2.refresh_from_db()
    assert alert2.incident is None  # Port scan is outside the window


# ── evaluate: CorrelationFiring dedup ────────────────────────────────────────


def test_dedup_links_new_alert_to_live_incident(org):
    from correlations.models import CorrelationFiring

    alert1 = _make_alert(org, title="port scan")
    alert2 = _make_alert(org, title="exploit attempt")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    # First evaluation: rule fires, incident created
    evaluate(alert2)

    alert1.refresh_from_db()
    alert2.refresh_from_db()
    assert alert1.incident is not None
    incident = alert1.incident

    assert CorrelationFiring.objects.filter(rule=rule, incident=incident).count() == 1

    # New alert matching leg1 arrives while firing is still live
    alert3 = _make_alert(org, title="port scan again")
    evaluate(alert3)

    alert3.refresh_from_db()
    assert alert3.incident == incident  # Linked to the same live incident
    assert CorrelationFiring.objects.filter(rule=rule).count() == 1  # No new firing


def test_dedup_no_new_incident_while_live(org):
    from correlations.models import CorrelationFiring
    from incidents.models import Incident

    alert1 = _make_alert(org, title="port scan")
    alert2 = _make_alert(org, title="exploit attempt")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert2)
    assert Incident.objects.count() == 1

    # Another alert that would satisfy both legs again
    alert3 = _make_alert(org, title="port scan again")
    alert4 = _make_alert(org, title="exploit attempt 2")
    evaluate(alert4)

    assert Incident.objects.count() == 1  # Still only one incident


def test_refire_allowed_after_incident_closes(org):
    from correlations.models import CorrelationFiring
    from incidents.models import Incident

    alert1 = _make_alert(org, title="port scan")
    alert2 = _make_alert(org, title="exploit attempt")
    rule = _make_rule(org, correlation_key="none", severity="high")
    leg1 = _make_leg(rule, count=1)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "port scan")
    _make_condition(leg2, FIELD_KIND_ALERT, "title", OPERATOR_CONTAINS, "exploit")

    evaluate(alert2)
    assert Incident.objects.count() == 1

    # Close the incident
    Incident.objects.update(state="closed")

    # New alerts arrive — rule should fire a new incident
    alert3 = _make_alert(org, title="port scan again")
    alert4 = _make_alert(org, title="exploit attempt 2")
    evaluate(alert4)

    assert Incident.objects.count() == 2
    assert CorrelationFiring.objects.count() == 2
