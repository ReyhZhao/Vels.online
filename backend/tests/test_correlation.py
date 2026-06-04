"""Tests for correlation rule leg matching and single-leg rule evaluation."""
import pytest
from security.models import Organization
from alerts.models import Alert, AlertEntity
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


def test_multi_leg_rule_skipped_in_this_slice(org):
    alert = _make_alert(org, severity="critical")
    rule = _make_rule(org, severity="high")
    leg1 = _make_leg(rule)
    leg2 = CorrelationRuleLeg.objects.create(rule=rule, count=1, display_order=1)
    _make_condition(leg1, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")
    _make_condition(leg2, FIELD_KIND_ALERT, "severity", OPERATOR_EQUALS, "critical")

    evaluate(alert)

    alert.refresh_from_db()
    assert alert.incident is None
