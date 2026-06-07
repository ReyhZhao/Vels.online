"""Tests for the evaluator decide/materialise split (ADR-0010, PRD #439 slice 1).

`decide()` runs the full firing decision (queries + key-join + Diversity Constraint)
and returns a Decision with NO side effects — no Alert/Incident/SearchFiring/SearchFinding.
OpenSearch is stubbed at the boundary (the `_search` method).
"""
from unittest.mock import MagicMock, patch

import pytest

from alerts.models import Alert
from correlations.models import (
    SEARCH_OPERATOR_CONTAINS,
    SearchFinding,
    SearchFiring,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
)
from correlations.services.search_evaluator import decide
from incidents.models import Incident
from security.models import Organization

_OS_CLIENT = "security.opensearch.OpenSearchClient"


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="DecideTest", slug="decidetest", wazuh_group="decidetest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _single_leg_rule(org, correlation_key="none"):
    r = SearchRule.objects.create(
        organization=org, name="Decide Rule", severity="high",
        correlation_key=correlation_key, window_minutes=60, interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1)
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS, value="brute force",
    )
    return r


def _hit(doc_id="d1"):
    return {
        "_id": doc_id, "_index": "vels-ruletest-x",
        "_source": {"rule": {"description": "brute force"}, "@timestamp": "2026-06-06T10:00:00Z"},
    }


def _now_window():
    from django.utils import timezone
    from datetime import timedelta
    now = timezone.now()
    return now, now - timedelta(minutes=60)


class TestDecideNoSideEffects:
    def test_decide_creates_no_db_rows(self, org):
        rule = _single_leg_rule(org)
        client = MagicMock()
        client._search.return_value = {"hits": {"hits": [_hit()], "total": {"value": 1}}}
        now, window_start = _now_window()

        decision = decide(rule, None, now, window_start, index="vels-ruletest-x", client=client)

        assert decision.would_fire is True
        assert Alert.objects.count() == 0
        assert Incident.objects.count() == 0
        assert SearchFiring.objects.count() == 0
        assert SearchFinding.objects.count() == 0

    def test_decide_uses_supplied_index_and_client(self, org):
        rule = _single_leg_rule(org)
        client = MagicMock()
        client._search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        now, window_start = _now_window()

        decide(rule, None, now, window_start, index="vels-ruletest-42", client=client)

        called_index = client._search.call_args[0][0]
        assert called_index == "vels-ruletest-42"


class TestDecideSingleLeg:
    def test_fires_when_hits_present(self, org):
        rule = _single_leg_rule(org)
        client = MagicMock()
        client._search.return_value = {"hits": {"hits": [_hit("a"), _hit("b")], "total": {"value": 2}}}
        now, window_start = _now_window()

        decision = decide(rule, None, now, window_start, client=client)

        assert decision.would_fire is True
        assert len(decision.units) == 1
        assert decision.units[0].key_value == "none"
        assert decision.diagnostics["mode"] == "single"
        assert decision.diagnostics["legs"][0]["matched"] == 2

    def test_does_not_fire_when_no_hits(self, org):
        rule = _single_leg_rule(org)
        client = MagicMock()
        client._search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
        now, window_start = _now_window()

        decision = decide(rule, None, now, window_start, client=client)

        assert decision.would_fire is False
        assert decision.units == []
        assert decision.diagnostics["satisfied_keys"] == []


class TestDecideMultiLeg:
    def _two_leg_rule(self, org):
        r = SearchRule.objects.create(
            organization=org, name="Multi", severity="high",
            correlation_key="host.name", window_minutes=60, interval_minutes=15,
            max_findings_per_run=50,
        )
        for i, val in enumerate(["brute force", "success"]):
            leg = SearchRuleLeg.objects.create(rule=r, display_order=i, count=1)
            SearchLegCondition.objects.create(
                leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS, value=val,
            )
        return r

    def test_fires_on_key_satisfying_all_legs(self, org):
        rule = self._two_leg_rule(org)
        client = MagicMock()
        agg = {"aggregations": {"key_agg": {"buckets": [{"key": "web-01", "doc_count": 3}]}}}
        hits = {"hits": {"hits": [_hit()], "total": {"value": 1}}}
        # 2 agg calls (one per leg), then per-key hit fetches (2 legs).
        client._search.side_effect = [agg, agg, hits, hits]
        now, window_start = _now_window()

        decision = decide(rule, None, now, window_start, client=client)

        assert decision.would_fire is True
        assert decision.units[0].key_value == "web-01"
        assert decision.diagnostics["satisfied_keys"] == ["web-01"]

    def test_no_fire_when_legs_share_no_key(self, org):
        rule = self._two_leg_rule(org)
        client = MagicMock()
        agg_a = {"aggregations": {"key_agg": {"buckets": [{"key": "web-01", "doc_count": 3}]}}}
        agg_b = {"aggregations": {"key_agg": {"buckets": [{"key": "web-02", "doc_count": 3}]}}}
        client._search.side_effect = [agg_a, agg_b]
        now, window_start = _now_window()

        decision = decide(rule, None, now, window_start, client=client)

        assert decision.would_fire is False
        assert decision.units == []
        assert SearchFiring.objects.count() == 0
