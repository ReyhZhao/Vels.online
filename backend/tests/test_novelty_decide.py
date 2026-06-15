"""Novelty Constraint — query compiler + decide path + novel-docs-only materialise (#523).

The decide path runs a stateless min-timestamp aggregation over the baseline lookback; a
(key, novelty value) is new iff its earliest sighting lands inside the detection boundary
(the run interval). OpenSearch is stubbed at the `_search` boundary. See ADR-0021.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from correlations.models import (
    SEARCH_OPERATOR_CONTAINS,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
)
from security.models import Organization

_OS_CLIENT = "security.opensearch.OpenSearchClient"
_WAZUH_CLIENT = "security.wazuh.WazuhClient"
_EXTRACT_IOCS = "incidents.services.ioc_extraction.extract_and_save_iocs"
_ACQUIRE_LOCK = "incidents.tasks.acquire_triage_lock"
_FAKE_AGENTS = [{"id": "001"}, {"id": "002"}]


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="NoveltyTest", slug="noveltytest", wazuh_group="noveltytest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


def _novelty_rule(org, interval_minutes=15, baseline_lookback_days=30):
    r = SearchRule.objects.create(
        organization=org, name="first logon", severity="high",
        correlation_key="user.name", window_minutes=60,
        interval_minutes=interval_minutes, baseline_lookback_days=baseline_lookback_days,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1, novelty_field="agent.name")
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS,
        value="authentication success",
    )
    return r


def _ms(dt):
    return dt.timestamp() * 1000.0


def _agg(now, *, novel_hosts=(), known_hosts=(), key="alice"):
    """Build a novelty agg response: novel_hosts first-seen recently, known_hosts long ago."""
    nb = []
    for h in novel_hosts:
        nb.append({"key": h, "first_seen": {"value": _ms(now - timedelta(minutes=2))}})
    for h in known_hosts:
        nb.append({"key": h, "first_seen": {"value": _ms(now - timedelta(days=10))}})
    return {"aggregations": {"key_agg": {"buckets": [
        {"key": key, "doc_count": len(nb), "novelty_agg": {"buckets": nb}},
    ]}}}


def _login_hit(host="db-prod-1", user="alice", doc_id="d1"):
    return {
        "_id": doc_id, "_index": "wazuh-alerts-4.x-test",
        "_source": {
            "rule": {"description": "authentication success"},
            "agent": {"name": host}, "data": {"dstuser": user},
            "@timestamp": "2026-06-15T10:00:00Z",
        },
    }


class TestNoveltyCompiler:
    def test_builds_terms_of_terms_with_min_timestamp(self):
        from correlations.services.search_compiler import compile_novelty_agg_query
        now = timezone.now()
        baseline_start = now - timedelta(days=30)
        body = compile_novelty_agg_query([], None, baseline_start, now, "data.dstuser", "agent.name")
        key_agg = body["aggregations"]["key_agg"]
        assert key_agg["terms"]["field"] == "data.dstuser"
        novelty_agg = key_agg["aggregations"]["novelty_agg"]
        assert novelty_agg["terms"]["field"] == "agent.name"
        assert novelty_agg["aggregations"]["first_seen"]["min"]["field"] == "@timestamp"
        assert body["size"] == 0
        ts_range = next(f["range"]["@timestamp"] for f in body["query"]["bool"]["filter"] if "range" in f)
        assert ts_range["gte"] == baseline_start.isoformat()


@pytest.mark.django_db
class TestNoveltyDecide:
    def test_fires_on_first_seen_host(self, org):
        from correlations.services.search_evaluator import decide
        rule = _novelty_rule(org)
        now = timezone.now()
        client = MagicMock()
        client._search.side_effect = [
            _agg(now, novel_hosts=["db-prod-1"], known_hosts=["web-01"]),
            {"hits": {"hits": [_login_hit()], "total": {"value": 1}}},
        ]
        decision = decide(rule, None, now, now - timedelta(minutes=60), client=client)
        assert decision.would_fire is True
        assert decision.diagnostics["mode"] == "novelty"
        assert decision.units[0].key_value == "alice"
        assert decision.units[0].novelty_info == {"agent.name": ["db-prod-1"]}
        assert len(decision.units[0].hits) == 1

    def test_does_not_fire_when_all_hosts_known(self, org):
        from correlations.services.search_evaluator import decide
        rule = _novelty_rule(org)
        now = timezone.now()
        client = MagicMock()
        client._search.side_effect = [_agg(now, known_hosts=["web-01", "db-prod-1"])]
        decision = decide(rule, None, now, now - timedelta(minutes=60), client=client)
        assert decision.would_fire is False
        assert decision.units == []
        assert client._search.call_count == 1  # no hit-fetch when nothing is new

    def test_hit_fetch_filters_to_novel_values_only(self, org):
        from correlations.services.search_evaluator import decide
        rule = _novelty_rule(org)
        now = timezone.now()
        client = MagicMock()
        client._search.side_effect = [
            _agg(now, novel_hosts=["db-prod-1"], known_hosts=["web-01"]),
            {"hits": {"hits": [_login_hit()], "total": {"value": 1}}},
        ]
        decide(rule, None, now, now - timedelta(minutes=60), client=client)
        hit_body = client._search.call_args_list[1][0][1]
        terms_filters = [f["terms"] for f in hit_body["query"]["bool"]["filter"] if "terms" in f]
        novel_terms = [t for t in terms_filters if "agent.name" in t]
        assert novel_terms == [{"agent.name": ["db-prod-1"]}]


@pytest.mark.django_db
class TestNoveltyFiring:
    def _run(self, rule, org, search_side_effect):
        from correlations.services.search_evaluator import run
        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = search_side_effect
            return run(rule, org)

    def test_first_logon_materialises_only_novel_doc(self, org):
        from alerts.models import Alert
        from incidents.models import Incident
        rule = _novelty_rule(org)
        now = timezone.now()
        incident = self._run(rule, org, [
            _agg(now, novel_hosts=["db-prod-1"], known_hosts=["web-01"]),
            {"hits": {"hits": [_login_hit()], "total": {"value": 1}}},
        ])
        assert incident is not None
        alerts = Alert.objects.filter(incident=incident)
        assert alerts.count() == 1
        assert alerts.first().source_ref["agent"]["name"] == "db-prod-1"
        assert "first-seen" in incident.title
        assert "db-prod-1" in incident.title
        assert Incident.objects.filter(organization=org).count() == 1

    def test_does_not_refire_once_host_is_known(self, org):
        from incidents.models import Incident
        rule = _novelty_rule(org)
        now = timezone.now()
        first = self._run(rule, org, [
            _agg(now, novel_hosts=["db-prod-1"]),
            {"hits": {"hits": [_login_hit()], "total": {"value": 1}}},
        ])
        second = self._run(rule, org, [_agg(timezone.now(), known_hosts=["db-prod-1"])])
        assert first is not None
        assert second is None
        assert Incident.objects.filter(organization=org).count() == 1
