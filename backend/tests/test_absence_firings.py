"""Tests for Absence Firings — configurable leg count operator (#519, ADR-0020).

Covers (external behaviour, stubbed OpenSearch/Wazuh):
- The leg threshold predicate (count_satisfies) for gte/lte including the 0 boundary.
- Rule validation: an `lte` leg is rejected with a non-none correlation key, accepted
  with `none`.
- The Absence Firing path: a zero-document window creates one zero-Alert Incident +
  a SearchFiring(finding_count=0); a persisting absence folds into the open Incident
  (no duplicate); a fresh Incident is created only after the prior one closes; a `gte`
  rule over the same empty window still creates nothing (regression).
- The absence description composer states the window and observed-vs-expected counts.
- Triage payload construction tolerates an Incident with zero linked Alerts.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from correlations.models import (
    SEARCH_COUNT_OP_GTE,
    SEARCH_COUNT_OP_LTE,
    SEARCH_OPERATOR_CONTAINS,
    SearchFiring,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
)
from correlations.services.leg_threshold import count_satisfies
from security.models import Organization

_WAZUH_CLIENT = "security.wazuh.WazuhClient"
_OS_CLIENT = "security.opensearch.OpenSearchClient"
_EXTRACT_IOCS = "incidents.services.ioc_extraction.extract_and_save_iocs"
_ACQUIRE_LOCK = "incidents.tasks.acquire_triage_lock"
_FAKE_AGENTS = [{"id": "001", "name": "web-01", "status": "active"}]


def _empty_os_response():
    return {"hits": {"hits": [], "total": {"value": 0}}}


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="AbsenceTest", slug="absencetest", wazuh_group="absencetest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _absence_rule(org, count=0):
    r = SearchRule.objects.create(
        organization=org, name="No firewall logs", severity="high",
        correlation_key="none", window_minutes=60, interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(
        rule=r, display_order=0, count=count, count_operator=SEARCH_COUNT_OP_LTE,
    )
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS, value="firewall",
    )
    return r


def _gte_rule(org):
    r = SearchRule.objects.create(
        organization=org, name="Brute force", severity="high",
        correlation_key="none", window_minutes=60, interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(
        rule=r, display_order=0, count=1, count_operator=SEARCH_COUNT_OP_GTE,
    )
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS, value="brute",
    )
    return r


# ── Predicate (deep module) ───────────────────────────────────────────────────

class TestCountSatisfies:
    @pytest.mark.parametrize("matched,threshold,expected", [
        (0, 1, False), (1, 1, True), (5, 1, True), (1, 3, False), (3, 3, True),
    ])
    def test_gte(self, matched, threshold, expected):
        assert count_satisfies(matched, SEARCH_COUNT_OP_GTE, threshold) is expected

    @pytest.mark.parametrize("matched,threshold,expected", [
        (0, 0, True), (1, 0, False), (0, 5, True), (5, 5, True), (6, 5, False),
    ])
    def test_lte(self, matched, threshold, expected):
        assert count_satisfies(matched, SEARCH_COUNT_OP_LTE, threshold) is expected

    def test_unknown_operator_defaults_to_gte(self):
        assert count_satisfies(2, "bogus", 1) is True
        assert count_satisfies(0, "bogus", 1) is False


# ── Validation: lte only with correlation_key = none ──────────────────────────

class TestAbsenceValidation:
    def _payload(self, correlation_key, count_operator):
        return {
            "name": "rule", "severity": "high",
            "correlation_key": correlation_key,
            "window_minutes": 60, "interval_minutes": 15,
            "legs": [{
                "count": 0, "count_operator": count_operator, "display_order": 0,
                "conditions": [{
                    "field_name": "rule.description", "operator": "contains", "value": "x",
                }],
            }],
        }

    @pytest.mark.django_db
    def test_lte_with_correlation_key_rejected(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value={}):
            ser = _SearchRuleSerializer(data=self._payload("host.name", SEARCH_COUNT_OP_LTE))
            assert not ser.is_valid()
        assert "legs" in ser.errors

    @pytest.mark.django_db
    def test_lte_with_none_key_accepted(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value={}):
            ser = _SearchRuleSerializer(data=self._payload("none", SEARCH_COUNT_OP_LTE))
            assert ser.is_valid(), ser.errors

    @pytest.mark.django_db
    def test_gte_with_correlation_key_accepted(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value={}):
            ser = _SearchRuleSerializer(data=self._payload("host.name", SEARCH_COUNT_OP_GTE))
            assert ser.is_valid(), ser.errors


# ── Absence Firing path ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAbsenceFiring:
    def _run(self, rule, org):
        from correlations.services.search_evaluator import run
        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _empty_os_response()
            return run(rule, org)

    def test_zero_docs_creates_zero_alert_incident(self, org):
        from alerts.models import Alert
        from incidents.models import Incident
        rule = _absence_rule(org)

        incident = self._run(rule, org)

        assert incident is not None
        assert incident.source_kind == "scheduled_search"
        assert Alert.objects.filter(incident=incident).count() == 0
        assert Alert.objects.filter(organization=org).count() == 0
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1
        firings = SearchFiring.objects.filter(rule=rule)
        assert firings.count() == 1
        assert firings.first().finding_count == 0
        assert "absence" in incident.description.lower()

    def test_persisting_absence_no_duplicate(self, org):
        from incidents.models import Incident
        rule = _absence_rule(org)

        first = self._run(rule, org)
        second = self._run(rule, org)

        assert first is not None
        assert second is None  # folded into the open incident
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1
        assert SearchFiring.objects.filter(rule=rule).count() == 1

    def test_new_incident_after_close(self, org):
        from incidents.models import Incident
        rule = _absence_rule(org)

        first = self._run(rule, org)
        first.state = "closed"
        first.save(update_fields=["state"])
        second = self._run(rule, org)

        assert second is not None
        assert second.id != first.id
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 2

    def test_gte_zero_docs_creates_nothing(self, org):
        """Regression: an ordinary gte rule over an empty window fires nothing."""
        from incidents.models import Incident
        rule = _gte_rule(org)

        result = self._run(rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org).exists()
        assert SearchFiring.objects.filter(rule=rule).count() == 0

    def test_triage_payload_tolerates_zero_alerts(self, org):
        from incidents.tasks import _build_triage_payload
        rule = _absence_rule(org)

        incident = self._run(rule, org)
        payload = _build_triage_payload(incident)

        assert payload["assets"] == []
        assert payload["iocs"] == []
        assert payload["source_kind"] == "scheduled_search"
        assert payload["description"] == incident.description


# ── Description composer ──────────────────────────────────────────────────────

class TestAbsenceDescription:
    def test_states_window_and_counts(self):
        from correlations.services.search_evaluator import (
            absence_title,
            compose_absence_description,
        )
        rule = MagicMock()
        rule.name = "No firewall logs"
        rule.description = "Alert when the firewall stops logging"
        leg = MagicMock()
        leg.count = 0
        now = timezone.now()
        start = now - timedelta(minutes=60)

        desc = compose_absence_description(rule, leg, start, now, matched_count=0)

        assert "absence" in desc.lower()
        assert start.isoformat() in desc
        assert now.isoformat() in desc
        assert "0" in desc
        assert "No firewall logs" in absence_title(rule)
