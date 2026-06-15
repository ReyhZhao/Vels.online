"""Novelty Constraint — Rule Test relative @timestamp offsets (#525, ADR-0021).

A novelty Rule Test must stage two eras of Sample Documents — a baseline doc (older than
the detection boundary) and a detection doc (within the last interval). Relative offsets
(now-40d, now-2m, …) let those eras be expressed durably; literal timestamps pass through.
"""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from correlations.models import (
    SEARCH_OPERATOR_CONTAINS,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
)
from security.models import Organization

_OS_CLIENT = "security.opensearch.OpenSearchClient"


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="NoveltyTest", slug="noveltytest", wazuh_group="noveltytest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _novelty_rule(org):
    r = SearchRule.objects.create(
        organization=org, name="first logon", severity="high",
        correlation_key="user.name", window_minutes=60,
        interval_minutes=15, baseline_lookback_days=30, max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1, novelty_field="agent.name")
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS,
        value="authentication success",
    )
    return r


class TestResolveSampleTimestamps:
    def _base(self):
        return datetime(2026, 6, 15, 12, 0, 0, tzinfo=dt_timezone.utc)

    def test_bare_now_resolves_to_base(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        base = self._base()
        out = resolve_sample_timestamps([{"@timestamp": "now"}], base)
        assert out[0]["@timestamp"] == base.isoformat()

    def test_negative_day_offset(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        base = self._base()
        out = resolve_sample_timestamps([{"@timestamp": "now-40d"}], base)
        assert out[0]["@timestamp"] == (base - timedelta(days=40)).isoformat()

    def test_minute_and_positive_offsets(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        base = self._base()
        out = resolve_sample_timestamps([{"@timestamp": "now-5m"}, {"@timestamp": "now+2h"}], base)
        assert out[0]["@timestamp"] == (base - timedelta(minutes=5)).isoformat()
        assert out[1]["@timestamp"] == (base + timedelta(hours=2)).isoformat()

    def test_literal_timestamp_passes_through(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        out = resolve_sample_timestamps([{"@timestamp": "2026-06-06T10:00:00Z"}], self._base())
        assert out[0]["@timestamp"] == "2026-06-06T10:00:00Z"

    def test_does_not_mutate_input(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        samples = [{"@timestamp": "now-1d", "rule": {"description": "x"}}]
        resolve_sample_timestamps(samples, self._base())
        assert samples[0]["@timestamp"] == "now-1d"

    def test_sample_without_timestamp_untouched(self):
        from correlations.services.search_test_runner import resolve_sample_timestamps
        out = resolve_sample_timestamps([{"rule": {"description": "x"}}], self._base())
        assert out == [{"rule": {"description": "x"}}]


@pytest.mark.django_db
class TestRuleTestResolvesBeforeIndexing:
    def test_relative_offsets_are_resolved_before_bulk_index(self, org):
        """The harness indexes absolute timestamps, never the raw 'now-Nd' tokens."""
        from correlations.services.search_test_runner import run_rule_test
        rule = _novelty_rule(org)
        m = MagicMock()
        m.get_raw_mapping.return_value = {"properties": {}}
        m._search.return_value = {
            "aggregations": {"key_agg": {"buckets": []}},
            "hits": {"hits": [], "total": {"value": 0}},
        }
        samples = [
            {"@timestamp": "now-10d", "agent": {"name": "web-01"}, "data": {"dstuser": "alice"},
             "rule": {"description": "authentication success"}},
            {"@timestamp": "now-2m", "agent": {"name": "db-prod-1"}, "data": {"dstuser": "alice"},
             "rule": {"description": "authentication success"}},
        ]
        with patch(_OS_CLIENT, return_value=m):
            run_rule_test(rule, samples, expect_fire=True)
        indexed = m.bulk_index.call_args[0][1]
        for doc in indexed:
            assert not doc["@timestamp"].startswith("now")
