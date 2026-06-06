"""Tests for Scheduled Search Rules — slice 1 (walking skeleton) + slice 2 (multi-leg co-occurrence).

Covers (external behaviour, stubbed OpenSearch/Wazuh):
- Compiler: operator → DSL, agent scoping, window bound, agg query shape, key filter
- Materialiser: idempotency + source_kind
- Evaluator: single-leg fire; multi-leg satisfied-key join; per-key incident creation;
  single-leg/none degenerate path still fires
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, call, patch

from django.utils import timezone

from correlations.models import (
    CORRELATION_KEY_NONE,
    SEARCH_OPERATOR_CIDR,
    SEARCH_OPERATOR_CONTAINS,
    SEARCH_OPERATOR_EQUALS,
    SEARCH_OPERATOR_GTE,
    SEARCH_OPERATOR_LTE,
    SearchFinding,
    SearchFiring,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
)
from correlations.services.search_compiler import (
    CORRELATION_KEY_TO_WAZUH_FIELD,
    compile_agg_query,
    compile_query,
    _condition_to_clause,
)
from security.models import Organization


# Patch targets — all imports are lazy (inside run()), so we patch at source modules.
_WAZUH_CLIENT = "security.wazuh.WazuhClient"
_OS_CLIENT = "security.opensearch.OpenSearchClient"
_EXTRACT_IOCS = "incidents.services.ioc_extraction.extract_and_save_iocs"
_ACQUIRE_LOCK = "incidents.tasks.acquire_triage_lock"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="SearchTest",
        slug="searchtest",
        wazuh_group="searchtest",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


@pytest.fixture
def rule(org):
    r = SearchRule.objects.create(
        organization=org,
        name="Test Search Rule",
        severity="high",
        window_minutes=60,
        interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0)
    SearchLegCondition.objects.create(
        leg=leg,
        field_name="rule.description",
        operator=SEARCH_OPERATOR_CONTAINS,
        value="brute force",
    )
    return r


def _make_condition(field_name, operator, value):
    """Build an unsaved condition-like object for compiler tests."""
    c = MagicMock()
    c.field_name = field_name
    c.operator = operator
    c.value = value
    return c


_FAKE_HIT = {
    "_id": "doc-abc-123",
    "_index": "wazuh-alerts-4.x-2026.06.01",
    "_source": {
        "agent": {"id": "001", "name": "web-01"},
        "rule": {"description": "brute force attempt", "level": 10},
        "@timestamp": "2026-06-06T10:00:00Z",
    },
}

_FAKE_AGENTS = [{"id": "001", "name": "web-01", "status": "active"}]


def _fake_opensearch_response(hits=None):
    if hits is None:
        hits = [_FAKE_HIT]
    return {"hits": {"hits": hits, "total": {"value": len(hits)}}}


# ── Compiler: operator → DSL ──────────────────────────────────────────────────

class TestSearchCompiler:
    def test_equals_produces_term(self):
        clause = _condition_to_clause(_make_condition("agent.name", SEARCH_OPERATOR_EQUALS, "web-01"))
        assert clause == {"term": {"agent.name": "web-01"}}

    def test_contains_produces_match(self):
        clause = _condition_to_clause(_make_condition("rule.description", SEARCH_OPERATOR_CONTAINS, "brute"))
        assert clause == {"match": {"rule.description": "brute"}}

    def test_gte_produces_range(self):
        clause = _condition_to_clause(_make_condition("rule.level", SEARCH_OPERATOR_GTE, "8"))
        assert clause == {"range": {"rule.level": {"gte": "8"}}}

    def test_lte_produces_range(self):
        clause = _condition_to_clause(_make_condition("rule.level", SEARCH_OPERATOR_LTE, "3"))
        assert clause == {"range": {"rule.level": {"lte": "3"}}}

    def test_cidr_produces_term(self):
        clause = _condition_to_clause(_make_condition("source.ip", SEARCH_OPERATOR_CIDR, "10.0.0.0/8"))
        assert clause == {"term": {"source.ip": "10.0.0.0/8"}}

    def test_unknown_operator_returns_none(self):
        clause = _condition_to_clause(_make_condition("x", "unknown_op", "v"))
        assert clause is None

    def test_compile_query_agent_scoping(self):
        agent_ids = ["001", "002"]
        now = timezone.now()
        window_start = now - timedelta(hours=1)
        body = compile_query([], agent_ids, window_start, now, 50)

        filter_clauses = body["query"]["bool"]["filter"]
        agent_clause = next(c for c in filter_clauses if "terms" in c)
        assert set(agent_clause["terms"]["agent.id"]) == {"001", "002"}

    def test_compile_query_window_bound(self):
        now = timezone.now()
        window_start = now - timedelta(hours=1)
        body = compile_query([], ["001"], window_start, now, 50)

        filter_clauses = body["query"]["bool"]["filter"]
        range_clause = next(c for c in filter_clauses if "range" in c)
        ts_range = range_clause["range"]["@timestamp"]
        assert ts_range["gte"] == window_start.isoformat()
        assert ts_range["lte"] == now.isoformat()

    def test_compile_query_respects_max_size(self):
        now = timezone.now()
        body = compile_query([], ["001"], now - timedelta(hours=1), now, 25)
        assert body["size"] == 25

    def test_compile_query_includes_condition_clauses(self):
        cond = _make_condition("rule.description", SEARCH_OPERATOR_CONTAINS, "brute")
        now = timezone.now()
        body = compile_query([cond], ["001"], now - timedelta(hours=1), now, 50)

        filter_clauses = body["query"]["bool"]["filter"]
        match_clauses = [c for c in filter_clauses if "match" in c]
        assert any(c["match"]["rule.description"] == "brute" for c in match_clauses)


# ── Materialiser: idempotency + source_kind ───────────────────────────────────

@pytest.mark.django_db
class TestMaterialiserIdempotency:
    def test_creates_alert_with_scheduled_search_source_kind(self, rule, org):
        from correlations.services.search_evaluator import run
        from alerts.models import Alert

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            run(rule, org)

        alert = Alert.objects.filter(organization=org, source_kind="scheduled_search").first()
        assert alert is not None
        assert alert.source_kind == "scheduled_search"

    def test_idempotent_for_same_doc(self, rule, org):
        """Running the evaluator twice for the same doc produces only one Alert."""
        from correlations.services.search_evaluator import run
        from alerts.models import Alert

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            run(rule, org)
            run(rule, org)  # Second run — same doc

        findings = SearchFinding.objects.filter(rule=rule)
        alerts = Alert.objects.filter(organization=org, source_kind="scheduled_search")
        assert findings.count() == 1
        assert alerts.count() == 1

    def test_no_findings_produces_no_incident(self, rule, org):
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response(hits=[])

            result = run(rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org, source_kind="scheduled_search").exists()


# ── Evaluator: single-leg fire creates a linked Incident ─────────────────────

@pytest.mark.django_db
class TestEvaluatorSingleLegFire:
    def test_creates_incident_with_correct_source_kind(self, rule, org):
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            incident = run(rule, org)

        assert incident is not None
        assert incident.source_kind == "scheduled_search"
        assert incident.organization == org

    def test_incident_severity_matches_rule(self, rule, org):
        from correlations.services.search_evaluator import run

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            incident = run(rule, org)

        assert incident.severity == rule.severity

    def test_alerts_linked_to_incident(self, rule, org):
        from correlations.services.search_evaluator import run
        from alerts.models import Alert

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            incident = run(rule, org)

        linked_alerts = Alert.objects.filter(incident=incident, source_kind="scheduled_search")
        assert linked_alerts.count() == 1
        assert linked_alerts.first().state == "imported"

    def test_search_firing_recorded(self, rule, org):
        from correlations.services.search_evaluator import run

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            incident = run(rule, org)

        firing = SearchFiring.objects.filter(rule=rule, organization=org).first()
        assert firing is not None
        assert firing.incident == incident
        assert firing.finding_count == 1

    def test_incident_visible_in_inbox(self, rule, org):
        """Incident appears when filtering by source_kind=scheduled_search."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            run(rule, org)

        assert Incident.objects.filter(
            organization=org, source_kind="scheduled_search"
        ).exists()

    def test_no_agents_returns_none(self, rule, org):
        """When WazuhClient returns no agents, run() returns None without querying OS."""
        from correlations.services.search_evaluator import run

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = []
            result = run(rule, org)
            MockOS.return_value._search.assert_not_called()

        assert result is None

    def test_opensearch_error_returns_none(self, rule, org):
        from correlations.services.search_evaluator import run
        from security.opensearch import OpenSearchError

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = OpenSearchError("connection refused")

            result = run(rule, org)

        assert result is None


# ── Schedule lifecycle ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestScheduleLifecycle:
    def test_sync_creates_periodic_task(self, rule):
        from correlations.services.search_schedule import sync_rule_schedule
        from django_celery_beat.models import PeriodicTask

        sync_rule_schedule(rule)

        pt = PeriodicTask.objects.get(name=f"search_rule_{rule.id}")
        assert pt.task == "correlations.tasks.run_scheduled_search_rule"
        assert pt.enabled is True
        assert pt.interval.every == rule.interval_minutes

    def test_sync_disables_when_rule_disabled(self, rule):
        from correlations.services.search_schedule import sync_rule_schedule
        from django_celery_beat.models import PeriodicTask

        sync_rule_schedule(rule)

        rule.enabled = False
        rule.save()
        sync_rule_schedule(rule)

        pt = PeriodicTask.objects.get(name=f"search_rule_{rule.id}")
        assert pt.enabled is False

    def test_delete_removes_periodic_task(self, rule):
        from correlations.services.search_schedule import delete_rule_schedule, sync_rule_schedule
        from django_celery_beat.models import PeriodicTask

        sync_rule_schedule(rule)
        delete_rule_schedule(rule)

        assert not PeriodicTask.objects.filter(name=f"search_rule_{rule.id}").exists()


# ── Compiler: agg query + key filter (slice 2) ───────────────────────────────

class TestSearchCompilerSlice2:
    def test_compile_agg_query_shape(self):
        now = timezone.now()
        window_start = now - timedelta(hours=1)
        body = compile_agg_query([], ["001"], window_start, now, "agent.name")

        assert body["size"] == 0
        agg = body["aggregations"]["key_agg"]["terms"]
        assert agg["field"] == "agent.name"
        assert agg["size"] == 500  # default max_buckets

    def test_compile_agg_query_carries_conditions(self):
        cond = _make_condition("rule.level", SEARCH_OPERATOR_GTE, "8")
        now = timezone.now()
        body = compile_agg_query([cond], ["001"], now - timedelta(hours=1), now, "agent.name")

        filters = body["query"]["bool"]["filter"]
        assert any("range" in c and c["range"].get("rule.level") for c in filters)

    def test_compile_query_key_filter_added(self):
        now = timezone.now()
        body = compile_query(
            [], ["001"], now - timedelta(hours=1), now, 50,
            key_field="agent.name", key_value="web-01",
        )
        filters = body["query"]["bool"]["filter"]
        assert {"term": {"agent.name": "web-01"}} in filters

    def test_compile_query_no_key_filter_when_omitted(self):
        now = timezone.now()
        body = compile_query([], ["001"], now - timedelta(hours=1), now, 50)
        filters = body["query"]["bool"]["filter"]
        # No extra term filter beyond agents + timestamp
        term_clauses = [c for c in filters if "term" in c]
        assert len(term_clauses) == 0

    def test_correlation_key_to_wazuh_field_map_complete(self):
        expected_keys = {"host.name", "source.ip", "user.name", "file.hash.sha256", "process.name"}
        assert expected_keys == set(CORRELATION_KEY_TO_WAZUH_FIELD.keys())


# ── Multi-leg evaluator (slice 2) ─────────────────────────────────────────────

def _make_agg_response(buckets):
    """Build a fake OpenSearch agg response."""
    return {
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {
            "key_agg": {
                "buckets": [{"key": k, "doc_count": v} for k, v in buckets.items()]
            }
        },
    }


def _make_hit(doc_id, key_field, key_value):
    return {
        "_id": doc_id,
        "_index": "wazuh-alerts-4.x-2026.06.01",
        "_source": {
            "agent": {"id": "001", "name": key_value},
            key_field: key_value,
            "rule": {"description": "test event", "level": 5},
            "@timestamp": "2026-06-06T10:00:00Z",
        },
    }


@pytest.fixture
def multi_leg_rule(org):
    """A two-leg rule with correlation_key=host.name."""
    r = SearchRule.objects.create(
        organization=org,
        name="Multi-leg Rule",
        severity="high",
        correlation_key="host.name",
        window_minutes=60,
        interval_minutes=15,
        max_findings_per_run=50,
    )
    leg1 = SearchRuleLeg.objects.create(rule=r, display_order=0, count=2)
    SearchLegCondition.objects.create(
        leg=leg1, field_name="rule.groups", operator=SEARCH_OPERATOR_EQUALS, value="authentication_failure"
    )
    leg2 = SearchRuleLeg.objects.create(rule=r, display_order=1, count=1)
    SearchLegCondition.objects.create(
        leg=leg2, field_name="rule.groups", operator=SEARCH_OPERATOR_EQUALS, value="authentication_success"
    )
    return r


@pytest.mark.django_db
class TestMultiLegEvaluator:
    def test_satisfied_key_creates_incident(self, multi_leg_rule, org):
        """When both legs meet their count for the same key an Incident is created."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg_response_leg1 = _make_agg_response({"web-01": 3, "web-02": 1})
        agg_response_leg2 = _make_agg_response({"web-01": 1, "web-03": 2})
        hit_response = _fake_opensearch_response(
            hits=[_make_hit("doc-1", "agent.name", "web-01")]
        )

        # agg calls first, then hit-fetch calls (one per leg per satisfied key)
        side_effects = [agg_response_leg1, agg_response_leg2, hit_response, hit_response]

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = side_effects

            result = run(multi_leg_rule, org)

        assert result is not None
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").exists()

    def test_no_satisfied_key_no_incident(self, multi_leg_rule, org):
        """When legs have no common key the rule does not fire."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        # leg1 satisfied for web-01; leg2 satisfied for web-03 — no intersection
        agg_response_leg1 = _make_agg_response({"web-01": 3})
        agg_response_leg2 = _make_agg_response({"web-03": 2})

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [agg_response_leg1, agg_response_leg2]

            result = run(multi_leg_rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org).exists()

    def test_only_leg_meeting_count_threshold_included(self, multi_leg_rule, org):
        """Key present in both aggs but below count for leg1 — should not fire."""
        from correlations.services.search_evaluator import run

        # leg1 requires count >= 2 but web-01 only has 1
        agg_response_leg1 = _make_agg_response({"web-01": 1})
        agg_response_leg2 = _make_agg_response({"web-01": 5})

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [agg_response_leg1, agg_response_leg2]

            result = run(multi_leg_rule, org)

        assert result is None

    def test_per_key_incident_creation(self, multi_leg_rule, org):
        """Two satisfied keys produce two Incidents."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        # Both keys satisfy both legs
        agg_response_leg1 = _make_agg_response({"web-01": 2, "web-02": 3})
        agg_response_leg2 = _make_agg_response({"web-01": 1, "web-02": 2})
        # 2 satisfied keys × 2 legs = 4 hit-fetch calls (sorted order: web-01, web-02)
        hit_web01 = _fake_opensearch_response(hits=[_make_hit("d1", "agent.name", "web-01")])
        hit_web02 = _fake_opensearch_response(hits=[_make_hit("d2", "agent.name", "web-02")])

        side_effects = [
            agg_response_leg1, agg_response_leg2,
            hit_web01, hit_web01,  # web-01 leg1 + leg2 hit fetches
            hit_web02, hit_web02,  # web-02 leg1 + leg2 hit fetches
        ]

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = side_effects

            run(multi_leg_rule, org)

        incidents = Incident.objects.filter(organization=org, source_kind="scheduled_search")
        assert incidents.count() == 2

    def test_single_leg_with_correlation_key_uses_degenerate_path(self, org):
        """A rule with correlation_key set but only one leg uses the simple path."""
        from correlations.services.search_evaluator import run

        r = SearchRule.objects.create(
            organization=org,
            name="Single Leg With Key",
            severity="medium",
            correlation_key="host.name",
            window_minutes=60,
            interval_minutes=15,
            max_findings_per_run=50,
        )
        leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1)
        SearchLegCondition.objects.create(
            leg=leg, field_name="rule.level", operator=SEARCH_OPERATOR_GTE, value="5"
        )

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            result = run(r, org)

        # Simple path: exactly one _search call (no agg)
        assert MockOS.return_value._search.call_count == 1
        assert result is not None

    def test_correlation_key_none_uses_degenerate_path(self, org):
        """A two-leg rule with correlation_key=none uses the simple single-leg path."""
        from correlations.services.search_evaluator import run

        r = SearchRule.objects.create(
            organization=org,
            name="None Key Two Legs",
            severity="medium",
            correlation_key=CORRELATION_KEY_NONE,
            window_minutes=60,
            interval_minutes=15,
            max_findings_per_run=50,
        )
        for i in range(2):
            leg = SearchRuleLeg.objects.create(rule=r, display_order=i, count=1)
            SearchLegCondition.objects.create(
                leg=leg, field_name="rule.level", operator=SEARCH_OPERATOR_GTE, value="5"
            )

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            result = run(r, org)

        # Simple path: exactly one _search call (uses first leg only)
        assert MockOS.return_value._search.call_count == 1
        assert result is not None

    def test_search_firing_records_key_value(self, multi_leg_rule, org):
        """SearchFiring.key_value is set to the correlation key value that fired."""
        from correlations.services.search_evaluator import run

        agg_response_leg1 = _make_agg_response({"db-server": 2})
        agg_response_leg2 = _make_agg_response({"db-server": 1})
        hit_response = _fake_opensearch_response(
            hits=[_make_hit("doc-x", "agent.name", "db-server")]
        )

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [
                agg_response_leg1, agg_response_leg2, hit_response, hit_response
            ]

            run(multi_leg_rule, org)

        firing = SearchFiring.objects.filter(rule=multi_leg_rule, organization=org).first()
        assert firing is not None
        assert firing.key_value == "db-server"


# ── Slice 3: dedup, overlapping-window idempotency, flood cap ─────────────────

_FAKE_HIT_2 = {
    "_id": "doc-xyz-456",
    "_index": "wazuh-alerts-4.x-2026.06.01",
    "_source": {
        "agent": {"id": "001", "name": "web-01"},
        "rule": {"description": "brute force attempt", "level": 10},
        "@timestamp": "2026-06-06T11:00:00Z",
    },
}


def _fake_overflow_response(hits, total):
    """Build a response where total > len(hits) (OpenSearch truncated the result)."""
    return {"hits": {"hits": hits, "total": {"value": total, "relation": "eq"}}}


@pytest.mark.django_db
class TestLiveFiringDedup:
    def test_new_findings_link_into_open_incident(self, rule, org):
        """Second run with a new doc links to the existing open incident, not a new one."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [
                _fake_opensearch_response(hits=[_FAKE_HIT]),
                _fake_opensearch_response(hits=[_FAKE_HIT_2]),
            ]

            incident1 = run(rule, org)
            incident2 = run(rule, org)

        assert incident1 is not None
        assert incident2 is not None
        assert incident1.id == incident2.id
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1
        assert incident1.alerts.filter(source_kind="scheduled_search").count() == 2

    def test_fresh_incident_created_after_close(self, rule, org):
        """After the prior incident is closed a second run with new docs produces a new Incident."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response(hits=[_FAKE_HIT])
            incident1 = run(rule, org)

        incident1.state = "closed"
        incident1.save(update_fields=["state", "updated_at"])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response(hits=[_FAKE_HIT_2])
            incident2 = run(rule, org)

        assert incident2 is not None
        assert incident1.id != incident2.id
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 2

    def test_overlapping_window_same_doc_no_new_incident(self, rule, org):
        """Re-running over an already-seen doc with an open incident produces no new Incident."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()

            run(rule, org)
            second = run(rule, org)

        assert second is None
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1

    def test_search_firing_created_per_run(self, rule, org):
        """Each run that links new findings creates its own SearchFiring record."""
        from correlations.services.search_evaluator import run

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [
                _fake_opensearch_response(hits=[_FAKE_HIT]),
                _fake_opensearch_response(hits=[_FAKE_HIT_2]),
            ]

            run(rule, org)
            run(rule, org)

        assert SearchFiring.objects.filter(rule=rule, organization=org).count() == 2


@pytest.mark.django_db
class TestFloodCap:
    def test_overflow_note_in_description(self, rule, org):
        """When OpenSearch total > returned hits, overflow note appears in incident description."""
        from correlations.services.search_evaluator import run

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_overflow_response(
                hits=[_FAKE_HIT], total=75
            )

            incident = run(rule, org)

        assert incident is not None
        assert "+74 more matched (truncated)" in incident.description

    def test_overflow_event_recorded(self, rule, org):
        """An overflow event is created on the incident when results are truncated."""
        from correlations.services.search_evaluator import run
        from incidents.models import IncidentEvent

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_overflow_response(
                hits=[_FAKE_HIT], total=120
            )

            incident = run(rule, org)

        event = IncidentEvent.objects.filter(
            incident=incident, kind="search_rule_overflow"
        ).first()
        assert event is not None
        assert event.payload["overflow"] == 119
        assert "+119 more matched (truncated)" in event.payload["note"]

    def test_overflow_event_on_live_incident(self, rule, org):
        """Overflow is recorded on an existing live incident (dedup + flood cap combined)."""
        from correlations.services.search_evaluator import run
        from incidents.models import IncidentEvent

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.side_effect = [
                _fake_opensearch_response(hits=[_FAKE_HIT]),
                _fake_overflow_response(hits=[_FAKE_HIT_2], total=60),
            ]

            incident1 = run(rule, org)
            incident2 = run(rule, org)

        assert incident1.id == incident2.id
        overflow_events = IncidentEvent.objects.filter(
            incident=incident1, kind="search_rule_overflow"
        )
        assert overflow_events.count() == 1
        assert overflow_events.first().payload["overflow"] == 59

    def test_no_overflow_when_total_equals_returned(self, rule, org):
        """No overflow event when OpenSearch total equals returned hits (no truncation)."""
        from correlations.services.search_evaluator import run
        from incidents.models import IncidentEvent

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response(hits=[_FAKE_HIT])

            incident = run(rule, org)

        assert not IncidentEvent.objects.filter(
            incident=incident, kind="search_rule_overflow"
        ).exists()
