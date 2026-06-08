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


# ── Slice 4: streaming suppression ───────────────────────────────────────────

@pytest.mark.django_db
class TestStreamingSuppression:
    """Materialised search-alerts must not participate in streaming correlation.

    Two suppression layers are tested:
    1. evaluate_correlation_rules task is a no-op for source_kind=scheduled_search.
    2. _get_window_alerts excludes scheduled_search from streaming window scans.
    """

    def _make_streaming_rule(self, org, count=1, match_title="brute force"):
        from correlations.models import (
            CorrelationRule, CorrelationRuleLeg, LegCondition,
            FIELD_KIND_ALERT, OPERATOR_CONTAINS,
        )
        rule = CorrelationRule.objects.create(
            organization=org,
            name="Streaming Rule",
            correlation_key="none",
            window_minutes=60,
            severity="critical",
            enabled=True,
        )
        leg = CorrelationRuleLeg.objects.create(rule=rule, count=count, display_order=0)
        LegCondition.objects.create(
            leg=leg,
            field_kind=FIELD_KIND_ALERT,
            field_name="title",
            operator=OPERATOR_CONTAINS,
            value=match_title,
        )
        return rule

    def _make_alert(self, org, source_kind, title="Test alert", severity="high", **kwargs):
        from alerts.models import Alert
        count = Alert.objects.count()
        return Alert.objects.create(
            organization=org,
            display_id=f"AL-{count + 1:04d}",
            source_kind=source_kind,
            source_ref={},
            title=title,
            severity=severity,
            state="new",
            **kwargs,
        )

    def test_evaluate_task_skips_scheduled_search_alert(self, org):
        """evaluate_correlation_rules task is a no-op for scheduled_search alerts."""
        from correlations.tasks import evaluate_correlation_rules
        from incidents.models import Incident

        self._make_streaming_rule(org, count=1, match_title="brute force")
        search_alert = self._make_alert(org, "scheduled_search", title="brute force: SSH")

        evaluate_correlation_rules(search_alert.id)

        search_alert.refresh_from_db()
        assert search_alert.incident is None
        assert Incident.objects.filter(source_kind="correlation").count() == 0

    def test_window_scan_excludes_scheduled_search(self, org):
        """_get_window_alerts never returns scheduled_search alerts."""
        from correlations.services.evaluator import _get_window_alerts
        from django.utils import timezone

        search_alert = self._make_alert(org, "scheduled_search", title="brute force: SSH")
        regular_alert = self._make_alert(org, "wazuh_event", title="Port scan")

        window_start = timezone.now() - timedelta(minutes=60)
        result = _get_window_alerts(org, "none", "none", window_start)

        result_ids = {a.id for a in result}
        assert search_alert.id not in result_ids
        assert regular_alert.id in result_ids

    def test_streaming_rule_does_not_fire_via_search_alert_in_window(self, org):
        """Evaluating an ordinary alert cannot satisfy a rule using a search-alert window hit."""
        from correlations.services.evaluator import evaluate
        from incidents.models import Incident

        # Rule needs 2 hits matching "brute force"; without suppression the search_alert
        # would be the first hit and the regular alert would be the second.
        self._make_streaming_rule(org, count=2, match_title="brute force")
        self._make_alert(org, "scheduled_search", title="brute force: SSH")
        regular_alert = self._make_alert(org, "wazuh_event", title="brute force: RDP")

        evaluate(regular_alert)

        regular_alert.refresh_from_db()
        assert regular_alert.incident is None
        assert Incident.objects.filter(source_kind="correlation").count() == 0

    def test_search_alert_incident_untouched_when_streaming_evaluates(self, org):
        """Evaluating an ordinary alert does not reassign a search-alert's incident."""
        from incidents.models import Incident
        from alerts.models import Alert
        from correlations.services.evaluator import evaluate

        # Create a search incident owning a search alert
        search_incident = Incident.objects.create(
            organization=org,
            display_id="INC-S001",
            title="Search Incident",
            severity="high",
            source_kind="scheduled_search",
            state="new",
            tlp="amber",
            pap="amber",
        )
        search_alert = Alert.objects.create(
            organization=org,
            display_id="AL-S001",
            source_kind="scheduled_search",
            source_ref={},
            title="brute force: SSH",
            severity="high",
            state="imported",
            incident=search_incident,
        )

        # A streaming rule with count=1 — without suppression it would fire and
        # _link_alert_to_incident would reassign search_alert to the correlation incident.
        self._make_streaming_rule(org, count=1, match_title="brute force")

        # Trigger evaluation via an ordinary alert that also matches the leg
        ordinary_alert = self._make_alert(org, "wazuh_event", title="brute force: RDP")
        evaluate(ordinary_alert)

        # The streaming rule fires for the ordinary alert (it satisfies count=1 by itself),
        # but the search_alert must remain linked to its own incident.
        search_alert.refresh_from_db()
        assert search_alert.incident_id == search_incident.id


# ── Slice 5: dynamic field catalog + mapping-aware validation ─────────────────

_STUB_MAPPING = {
    "rule.id":          "keyword",
    "rule.level":       "long",
    "rule.description": "text",
    "rule.groups":      "keyword",
    "agent.name":       "keyword",
    "data.srcip":       "ip",
}


class TestValidateSearchField:
    """Pure-function tests for validate_search_field — no DB or OS needed."""

    def setup_method(self):
        from correlations.services.search_compiler import validate_search_field
        self.validate = validate_search_field

    def test_valid_keyword_equals(self):
        ok, msg = self.validate("rule.id", SEARCH_OPERATOR_EQUALS, _STUB_MAPPING)
        assert ok is True
        assert msg == ""

    def test_valid_long_gte(self):
        ok, msg = self.validate("rule.level", SEARCH_OPERATOR_GTE, _STUB_MAPPING)
        assert ok is True

    def test_valid_long_lte(self):
        ok, msg = self.validate("rule.level", SEARCH_OPERATOR_LTE, _STUB_MAPPING)
        assert ok is True

    def test_valid_ip_cidr(self):
        ok, msg = self.validate("data.srcip", SEARCH_OPERATOR_CIDR, _STUB_MAPPING)
        assert ok is True

    def test_valid_text_contains(self):
        ok, msg = self.validate("rule.description", SEARCH_OPERATOR_CONTAINS, _STUB_MAPPING)
        assert ok is True

    def test_valid_text_equals(self):
        # text + equals is valid — translator emits .keyword suffix
        ok, msg = self.validate("rule.description", SEARCH_OPERATOR_EQUALS, _STUB_MAPPING)
        assert ok is True

    def test_absent_field_rejected(self):
        ok, msg = self.validate("nonexistent.field", SEARCH_OPERATOR_EQUALS, _STUB_MAPPING)
        assert ok is False
        assert "nonexistent.field" in msg
        assert "mapping" in msg.lower()

    def test_type_mismatch_cidr_on_keyword_rejected(self):
        ok, msg = self.validate("rule.id", SEARCH_OPERATOR_CIDR, _STUB_MAPPING)
        assert ok is False
        assert "cidr" in msg.lower() or "not valid" in msg.lower()

    def test_type_mismatch_gte_on_ip_rejected(self):
        ok, msg = self.validate("data.srcip", SEARCH_OPERATOR_GTE, _STUB_MAPPING)
        assert ok is False

    def test_type_mismatch_gte_on_keyword_rejected(self):
        ok, msg = self.validate("agent.name", SEARCH_OPERATOR_GTE, _STUB_MAPPING)
        assert ok is False

    def test_empty_mapping_bypasses_validation(self):
        # When the mapping cannot be fetched, validation is skipped.
        ok, msg = self.validate("any.field", SEARCH_OPERATOR_EQUALS, {})
        assert ok is True

    def test_error_message_contains_valid_operators(self):
        ok, msg = self.validate("rule.level", SEARCH_OPERATOR_CIDR, _STUB_MAPPING)
        assert ok is False
        # Message should tell the user which operators are valid for this type
        assert "equals" in msg or "gte" in msg or "lte" in msg


class TestIsAggregatableField:
    """is_aggregatable_field: text is non-aggregatable, keyword/ip/long are."""

    def setup_method(self):
        from correlations.services.search_compiler import is_aggregatable_field
        self.check = is_aggregatable_field

    def test_keyword_is_aggregatable(self):
        assert self.check("rule.id", _STUB_MAPPING) is True

    def test_long_is_aggregatable(self):
        assert self.check("rule.level", _STUB_MAPPING) is True

    def test_ip_is_aggregatable(self):
        assert self.check("data.srcip", _STUB_MAPPING) is True

    def test_text_is_not_aggregatable(self):
        assert self.check("rule.description", _STUB_MAPPING) is False

    def test_unknown_field_defaults_to_aggregatable(self):
        # Fields absent from mapping get "keyword" default — they are aggregatable.
        assert self.check("unknown.field", _STUB_MAPPING) is True


class TestTypeAwareCompilerClause:
    """_condition_to_clause uses field_mapping to select the correct DSL form."""

    def test_text_equals_uses_keyword_subfield(self):
        cond = _make_condition("rule.description", SEARCH_OPERATOR_EQUALS, "SSH")
        mapping = {"rule.description": "text"}
        clause = _condition_to_clause(cond, field_mapping=mapping)
        assert clause == {"term": {"rule.description.keyword": "SSH"}}

    def test_keyword_equals_uses_plain_term(self):
        cond = _make_condition("rule.id", SEARCH_OPERATOR_EQUALS, "5710")
        mapping = {"rule.id": "keyword"}
        clause = _condition_to_clause(cond, field_mapping=mapping)
        assert clause == {"term": {"rule.id": "5710"}}

    def test_ip_cidr_uses_term(self):
        cond = _make_condition("data.srcip", SEARCH_OPERATOR_CIDR, "10.0.0.0/8")
        mapping = {"data.srcip": "ip"}
        clause = _condition_to_clause(cond, field_mapping=mapping)
        assert clause == {"term": {"data.srcip": "10.0.0.0/8"}}

    def test_long_gte_uses_range(self):
        cond = _make_condition("rule.level", SEARCH_OPERATOR_GTE, "8")
        mapping = {"rule.level": "long"}
        clause = _condition_to_clause(cond, field_mapping=mapping)
        assert clause == {"range": {"rule.level": {"gte": "8"}}}

    def test_no_mapping_falls_back_to_keyword_behaviour(self):
        cond = _make_condition("rule.id", SEARCH_OPERATOR_EQUALS, "42")
        clause = _condition_to_clause(cond, field_mapping=None)
        assert clause == {"term": {"rule.id": "42"}}

    def test_compile_query_passes_mapping_through(self):
        cond = _make_condition("rule.description", SEARCH_OPERATOR_EQUALS, "brute")
        now = timezone.now()
        body = compile_query(
            [cond], ["001"], now - timedelta(hours=1), now, 50,
            field_mapping={"rule.description": "text"},
        )
        filters = body["query"]["bool"]["filter"]
        term_clauses = [f for f in filters if "term" in f]
        assert any("rule.description.keyword" in c["term"] for c in term_clauses)


class TestGetFieldMappingClient:
    """OpenSearchClient.get_field_mapping: HTTP call, flatten, TTL cache."""

    def _mapping_response(self, properties: dict):
        m = MagicMock()
        m.raise_for_status.return_value = None
        m.json.return_value = {
            "wazuh-alerts-4.x-000001": {
                "mappings": {"properties": properties}
            }
        }
        return m

    @patch("security.opensearch.requests.get")
    def test_flattens_nested_properties(self, mock_get, monkeypatch):
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        # Clear module-level cache
        import security.opensearch as os_mod
        os_mod._field_mapping_cache.clear()

        mock_get.return_value = self._mapping_response({
            "rule": {
                "properties": {
                    "id": {"type": "keyword"},
                    "level": {"type": "long"},
                    "description": {"type": "text"},
                }
            },
            "data": {
                "properties": {
                    "srcip": {"type": "ip"},
                }
            },
        })

        from security.opensearch import OpenSearchClient
        mapping = OpenSearchClient().get_field_mapping()

        assert mapping["rule.id"] == "keyword"
        assert mapping["rule.level"] == "long"
        assert mapping["rule.description"] == "text"
        assert mapping["data.srcip"] == "ip"

    @patch("security.opensearch.requests.get")
    def test_ttl_cache_avoids_second_call(self, mock_get, monkeypatch):
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._field_mapping_cache.clear()

        mock_get.return_value = self._mapping_response({"rule": {"properties": {"id": {"type": "keyword"}}}})

        from security.opensearch import OpenSearchClient
        c = OpenSearchClient()
        c.get_field_mapping()
        c.get_field_mapping()
        assert mock_get.call_count == 1

    @patch("security.opensearch.requests.get")
    def test_http_error_raises_opensearch_error(self, mock_get, monkeypatch):
        import requests as req_mod
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._field_mapping_cache.clear()

        resp = MagicMock()
        resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError("500")
        mock_get.return_value = resp

        from security.opensearch import OpenSearchClient, OpenSearchError
        with pytest.raises(OpenSearchError):
            OpenSearchClient().get_field_mapping()


class TestGetRuleCatalogClient:
    """OpenSearchClient.get_rule_catalog: terms agg, TTL cache, agent scoping."""

    def _catalog_response(self, buckets):
        m = MagicMock()
        m.raise_for_status.return_value = None
        m.json.return_value = {
            "hits": {"hits": [], "total": {"value": 0}},
            "aggregations": {"by_rule_id": {"buckets": buckets}},
        }
        return m

    @patch("security.opensearch.requests.post")
    def test_returns_keyed_catalog(self, mock_post, monkeypatch):
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._rule_catalog_cache.clear()

        mock_post.return_value = self._catalog_response([{
            "key": "5710",
            "doc_count": 42,
            "desc": {"buckets": [{"key": "SSH brute force"}]},
            "groups": {"buckets": [{"key": "authentication"}, {"key": "ssh"}]},
            "level": {"buckets": [{"key": 10}]},
        }])

        from security.opensearch import OpenSearchClient
        catalog = OpenSearchClient().get_rule_catalog()

        assert "5710" in catalog
        entry = catalog["5710"]
        assert entry["description"] == "SSH brute force"
        assert "authentication" in entry["groups"]
        assert entry["level"] == 10
        assert entry["seen_count"] == 42

    @patch("security.opensearch.requests.post")
    def test_agent_ids_added_as_filter(self, mock_post, monkeypatch):
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._rule_catalog_cache.clear()

        mock_post.return_value = self._catalog_response([])

        from security.opensearch import OpenSearchClient
        OpenSearchClient().get_rule_catalog(agent_ids=["001", "002"])

        body = mock_post.call_args[1]["json"]
        filters = body["query"]["bool"]["filter"]
        agent_filter = next(f for f in filters if "terms" in f)
        assert set(agent_filter["terms"]["agent.id"]) == {"001", "002"}

    @patch("security.opensearch.requests.post")
    def test_ttl_cache_avoids_second_call(self, mock_post, monkeypatch):
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._rule_catalog_cache.clear()

        mock_post.return_value = self._catalog_response([])

        from security.opensearch import OpenSearchClient
        c = OpenSearchClient()
        c.get_rule_catalog()
        c.get_rule_catalog()
        assert mock_post.call_count == 1

    @patch("security.opensearch.requests.post")
    def test_opensearch_error_returns_empty_dict(self, mock_post, monkeypatch):
        import requests as req_mod
        monkeypatch.setenv("WAZUH_INDEXER_URL", "https://os.test:9200")
        monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
        monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")
        import security.opensearch as os_mod
        os_mod._rule_catalog_cache.clear()

        resp = MagicMock()
        resp.raise_for_status.side_effect = req_mod.exceptions.HTTPError("500")
        mock_post.return_value = resp

        from security.opensearch import OpenSearchClient
        result = OpenSearchClient().get_rule_catalog()
        assert result == {}


@pytest.mark.django_db
class TestSearchRuleConditionValidation:
    """SearchRule create/update rejects conditions that fail mapping validation."""

    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("staff@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _rule_payload(self, org, field_name, operator="equals"):
        return {
            "organization": org.pk,
            "name": "Validation Test",
            "severity": "high",
            "correlation_key": "none",
            "window_minutes": 60,
            "interval_minutes": 15,
            "max_findings_per_run": 50,
            "enabled": True,
            "legs": [{
                "count": 1,
                "display_order": 0,
                "conditions": [{
                    "field_name": field_name,
                    "operator": operator,
                    "value": "test",
                }],
            }],
        }

    @patch("correlations.views._get_mapping_safe")
    def test_valid_condition_accepted(self, mock_mapping, org):
        mock_mapping.return_value = {"rule.id": "keyword"}
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            client = self._staff_client()
            resp = client.post(
                "/api/correlations/search-rules/",
                self._rule_payload(org, "rule.id", "equals"),
                format="json",
            )
        assert resp.status_code == 201

    @patch("correlations.views._get_mapping_safe")
    def test_absent_field_rejected_with_400(self, mock_mapping, org):
        mock_mapping.return_value = {"rule.id": "keyword"}
        client = self._staff_client()
        resp = client.post(
            "/api/correlations/search-rules/",
            self._rule_payload(org, "nonexistent.field", "equals"),
            format="json",
        )
        assert resp.status_code == 400

    @patch("correlations.views._get_mapping_safe")
    def test_operator_type_mismatch_rejected_with_400(self, mock_mapping, org):
        # rule.id is keyword — cidr is only valid for ip
        mock_mapping.return_value = {"rule.id": "keyword"}
        client = self._staff_client()
        resp = client.post(
            "/api/correlations/search-rules/",
            self._rule_payload(org, "rule.id", "cidr"),
            format="json",
        )
        assert resp.status_code == 400

    @patch("correlations.views._get_mapping_safe")
    def test_unavailable_mapping_allows_save(self, mock_mapping, org):
        # When mapping is empty (fetch failed), validation is skipped.
        mock_mapping.return_value = {}
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            client = self._staff_client()
            resp = client.post(
                "/api/correlations/search-rules/",
                self._rule_payload(org, "any.arbitrary.field", "equals"),
                format="json",
            )
        assert resp.status_code == 201

    @patch("correlations.views._get_mapping_safe")
    def test_text_field_as_correlation_key_rejected(self, mock_mapping, org):
        """A correlation_key that maps to a text Wazuh field must be rejected."""
        # Override CORRELATION_KEY_TO_WAZUH_FIELD to map "host.name" → a text field in mapping
        mock_mapping.return_value = {"agent.name": "text"}  # normally keyword, but force text
        client = self._staff_client()
        payload = {
            "organization": org.pk,
            "name": "Text Key Test",
            "severity": "medium",
            "correlation_key": "host.name",
            "window_minutes": 60,
            "interval_minutes": 15,
            "max_findings_per_run": 50,
            "enabled": True,
            "legs": [],
        }
        resp = client.post("/api/correlations/search-rules/", payload, format="json")
        assert resp.status_code == 400
        assert "correlation_key" in resp.data


# ── Slice 6: System Rules (per-org fan-out, mute, failure isolation) ──────────

@pytest.fixture
def system_rule(db):
    """A SearchRule with organization=None (system rule)."""
    r = SearchRule.objects.create(
        organization=None,
        name="System Brute Force",
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


@pytest.fixture
def org2(db):
    return Organization.objects.create(
        name="SecondOrg",
        slug="secondorg",
        wazuh_group="secondorg",
        alert_match_lookback_days=30,
        alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


class TestSystemRuleFanOut:
    """System rules iterate all orgs; muted orgs are skipped; per-org failures are isolated."""

    def test_fanout_produces_incident_per_org(self, system_rule, org, org2):
        """Fan-out over two orgs produces two separate firings (one incident each).

        Each org has distinct document IDs (real orgs see different agents), so
        the SearchFinding idempotency guard does not suppress the second org.
        """
        from correlations.services.search_evaluator import run

        def hit_for(doc_id):
            return {
                "_id": doc_id,
                "_index": "wazuh-alerts-4.x-2026.06.01",
                "_source": {
                    "agent": {"id": "001", "name": "agent"},
                    "rule": {"description": "brute force attempt", "level": 10},
                    "@timestamp": "2026-06-06T10:00:00Z",
                },
            }

        with (
            patch(_WAZUH_CLIENT) as mock_wazuh,
            patch(_OS_CLIENT) as mock_os,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            mock_wazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            mock_os.return_value._search.side_effect = [
                _fake_opensearch_response([hit_for("doc-org1-001")]),
                _fake_opensearch_response([hit_for("doc-org2-001")]),
            ]

            run(system_rule, org)
            run(system_rule, org2)

        org_firings = SearchFiring.objects.filter(rule=system_rule, organization=org)
        org2_firings = SearchFiring.objects.filter(rule=system_rule, organization=org2)
        assert org_firings.count() == 1
        assert org2_firings.count() == 1
        # Incidents are tenant-isolated
        assert org_firings.first().incident.organization == org
        assert org2_firings.first().incident.organization == org2

    def test_fanout_task_skips_muted_org(self, system_rule, org, org2):
        """run_scheduled_search_rule skips orgs that have muted the system rule."""
        from correlations.models import SearchRuleMute
        from correlations.tasks import run_scheduled_search_rule

        SearchRuleMute.objects.create(organization=org, rule=system_rule)

        with (
            patch(_WAZUH_CLIENT) as mock_wazuh,
            patch(_OS_CLIENT) as mock_os,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            mock_wazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            mock_os.return_value._search.return_value = _fake_opensearch_response()

            run_scheduled_search_rule(system_rule.id)

        # org muted — no firing for it
        assert SearchFiring.objects.filter(rule=system_rule, organization=org).count() == 0
        # org2 not muted — fired
        assert SearchFiring.objects.filter(rule=system_rule, organization=org2).count() == 1

    def test_per_org_failure_does_not_abort_others(self, system_rule, org, org2):
        """If one org's OpenSearch call raises, the other orgs still complete."""
        from correlations.tasks import run_scheduled_search_rule
        from security.opensearch import OpenSearchError

        call_count = {"n": 0}

        def side_effect_search(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OpenSearchError("simulated failure")
            return _fake_opensearch_response()

        with (
            patch(_WAZUH_CLIENT) as mock_wazuh,
            patch(_OS_CLIENT) as mock_os,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            mock_wazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            mock_os.return_value._search.side_effect = side_effect_search

            # Should not raise despite first org failing
            run_scheduled_search_rule(system_rule.id)

        # At least one org succeeded (the second one)
        total_firings = SearchFiring.objects.filter(rule=system_rule).count()
        assert total_firings >= 1

    def test_no_cross_tenant_incident(self, system_rule, org, org2):
        """Incidents created for org do not include alerts belonging to org2."""
        from correlations.services.search_evaluator import run

        def org_hit(org_slug):
            return {
                "_id": f"doc-{org_slug}",
                "_index": "wazuh-alerts-4.x-2026.06.01",
                "_source": {
                    "agent": {"id": "001", "name": f"agent-{org_slug}"},
                    "rule": {"description": "brute force attempt", "level": 10},
                    "@timestamp": "2026-06-06T10:00:00Z",
                },
            }

        with (
            patch(_WAZUH_CLIENT) as mock_wazuh,
            patch(_OS_CLIENT) as mock_os,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            mock_wazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            mock_os.return_value._search.side_effect = [
                _fake_opensearch_response([org_hit("org1")]),
                _fake_opensearch_response([org_hit("org2")]),
            ]

            run(system_rule, org)
            run(system_rule, org2)

        firing_org = SearchFiring.objects.get(rule=system_rule, organization=org)
        firing_org2 = SearchFiring.objects.get(rule=system_rule, organization=org2)
        # Incidents are distinct and org-scoped
        assert firing_org.incident_id != firing_org2.incident_id
        assert firing_org.incident.organization_id == org.id
        assert firing_org2.incident.organization_id == org2.id

    def test_org_rule_still_runs_for_its_org_only(self, rule, org, org2):
        """An org-scoped rule only runs for its own org (no fan-out)."""
        from correlations.tasks import run_scheduled_search_rule

        with (
            patch(_WAZUH_CLIENT) as mock_wazuh,
            patch(_OS_CLIENT) as mock_os,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            mock_wazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            mock_os.return_value._search.return_value = _fake_opensearch_response()

            run_scheduled_search_rule(rule.id)

        assert SearchFiring.objects.filter(rule=rule, organization=org).count() == 1
        assert SearchFiring.objects.filter(rule=rule, organization=org2).count() == 0


class TestSystemSearchRuleMuteAPI:
    """OrgSystemSearchRulesView and OrgSystemSearchRuleMuteView."""

    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("staff2@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_list_system_search_rules_includes_mute_status(self, system_rule, org):
        client = self._staff_client()
        resp = client.get(f"/api/correlations/org-system-search-rules/?org={org.slug}")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        row = resp.data[0]
        assert row["id"] == system_rule.id
        assert row["muted"] is False

    def test_mute_creates_record(self, system_rule, org):
        from correlations.models import SearchRuleMute
        client = self._staff_client()
        resp = client.post(
            f"/api/correlations/org-system-search-rules/{system_rule.id}/mute/",
            {"org": org.slug},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["muted"] is True
        assert SearchRuleMute.objects.filter(organization=org, rule=system_rule).exists()

    def test_unmute_removes_record(self, system_rule, org):
        from correlations.models import SearchRuleMute
        SearchRuleMute.objects.create(organization=org, rule=system_rule)
        client = self._staff_client()
        resp = client.delete(
            f"/api/correlations/org-system-search-rules/{system_rule.id}/mute/?org={org.slug}",
        )
        assert resp.status_code == 200
        assert resp.data["muted"] is False
        assert not SearchRuleMute.objects.filter(organization=org, rule=system_rule).exists()

    def test_list_reflects_muted_state(self, system_rule, org):
        from correlations.models import SearchRuleMute
        SearchRuleMute.objects.create(organization=org, rule=system_rule)
        client = self._staff_client()
        resp = client.get(f"/api/correlations/org-system-search-rules/?org={org.slug}")
        assert resp.status_code == 200
        assert resp.data[0]["muted"] is True

    def test_org_rule_not_returned_as_system_rule(self, rule, org):
        """Org-scoped rules must not appear in the system search rules list."""
        client = self._staff_client()
        resp = client.get(f"/api/correlations/org-system-search-rules/?org={org.slug}")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.data]
        assert rule.id not in ids

    def test_mute_idempotent(self, system_rule, org):
        """POSTing mute twice does not error or create duplicate records."""
        from correlations.models import SearchRuleMute
        client = self._staff_client()
        client.post(
            f"/api/correlations/org-system-search-rules/{system_rule.id}/mute/",
            {"org": org.slug},
            format="json",
        )
        resp = client.post(
            f"/api/correlations/org-system-search-rules/{system_rule.id}/mute/",
            {"org": org.slug},
            format="json",
        )
        assert resp.status_code == 200
        assert SearchRuleMute.objects.filter(organization=org, rule=system_rule).count() == 1

    def test_non_staff_cannot_list(self, system_rule, org):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("nostaff@test.com", password="x", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get(f"/api/correlations/org-system-search-rules/?org={org.slug}")
        assert resp.status_code == 403


# ── Diversity Constraint (ADR-0009) — slice 1: validator + compiler + evaluator ─

_DIV_MAPPING = {
    "GeoLocation.country_name": "keyword",
    "data.dstuser": "keyword",
    "rule.description": "text",
    "rule.groups": "keyword",
}


class TestValidateDiversityConstraint:
    """Pure-function tests for the four Diversity Constraint invariants."""

    def setup_method(self):
        from correlations.services.search_compiler import validate_diversity_constraint
        self.v = validate_diversity_constraint

    def test_empty_field_is_no_constraint(self):
        ok, msg = self.v("", 2, "user.name", _DIV_MAPPING)
        assert ok is True and msg == ""

    def test_none_key_rejected(self):
        ok, msg = self.v("GeoLocation.country_name", 2, "none", _DIV_MAPPING)
        assert ok is False
        assert "correlation key" in msg.lower()

    def test_min_distinct_below_two_rejected(self):
        ok, msg = self.v("GeoLocation.country_name", 1, "user.name", _DIV_MAPPING)
        assert ok is False
        assert "at least 2" in msg

    def test_non_aggregatable_field_rejected(self):
        ok, msg = self.v("rule.description", 2, "user.name", _DIV_MAPPING)
        assert ok is False
        assert "non-aggregatable" in msg.lower() or "text" in msg.lower()

    def test_same_as_correlation_key_field_rejected(self):
        # user.name → data.dstuser; diversifying on the key field is a dead rule.
        ok, msg = self.v("data.dstuser", 2, "user.name", _DIV_MAPPING)
        assert ok is False
        assert "differ" in msg.lower()

    def test_absent_field_rejected(self):
        ok, msg = self.v("nope.field", 2, "user.name", _DIV_MAPPING)
        assert ok is False
        assert "does not exist" in msg.lower()

    def test_valid_constraint_accepted(self):
        ok, msg = self.v("GeoLocation.country_name", 2, "user.name", _DIV_MAPPING)
        assert ok is True and msg == ""

    def test_empty_mapping_bypasses_type_check(self):
        ok, msg = self.v("any.field", 2, "user.name", {})
        assert ok is True


class TestDiversityCompiler:
    """compile_agg_query nests a size-capped terms sub-agg when distinct_field is set."""

    def _now_window(self):
        now = timezone.now()
        return now - timedelta(hours=1), now

    def test_distinct_subagg_added(self):
        ws, now = self._now_window()
        body = compile_agg_query([], ["001"], ws, now, "data.dstuser",
                                 distinct_field="GeoLocation.country_name")
        sub = body["aggregations"]["key_agg"]["aggregations"]["distinct_agg"]["terms"]
        assert sub["field"] == "GeoLocation.country_name"
        assert sub["size"] == 50

    def test_distinct_subagg_keyword_resolution_for_text(self):
        ws, now = self._now_window()
        body = compile_agg_query([], ["001"], ws, now, "data.dstuser",
                                 distinct_field="GeoLocation.country_name",
                                 field_mapping={"GeoLocation.country_name": "text"})
        sub = body["aggregations"]["key_agg"]["aggregations"]["distinct_agg"]["terms"]
        assert sub["field"] == "GeoLocation.country_name.keyword"

    def test_no_subagg_when_distinct_field_omitted(self):
        ws, now = self._now_window()
        body = compile_agg_query([], ["001"], ws, now, "data.dstuser")
        assert "aggregations" not in body["aggregations"]["key_agg"]


def _make_div_agg_response(buckets):
    """buckets: {key_value: [(distinct_value, count), ...]} → fake agg response with sub-agg."""
    return {
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {"key_agg": {"buckets": [
            {
                "key": k,
                "doc_count": sum(c for _, c in dvals),
                "distinct_agg": {"buckets": [{"key": dv, "doc_count": c} for dv, c in dvals]},
            }
            for k, dvals in buckets.items()
        ]}},
    }


@pytest.fixture
def diversity_rule(org):
    """Single-leg impossible-travel-lite rule: ≥2 logins spanning ≥2 countries per user."""
    r = SearchRule.objects.create(
        organization=org,
        name="Impossible Travel",
        severity="high",
        correlation_key="user.name",
        window_minutes=60,
        interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(
        rule=r, display_order=0, count=2,
        distinct_field="GeoLocation.country_name", min_distinct=2,
    )
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.groups",
        operator=SEARCH_OPERATOR_EQUALS, value="authentication_success",
    )
    return r


@pytest.mark.django_db
class TestSingleLegDiversityEvaluator:
    def test_fires_when_distinct_threshold_met(self, diversity_rule, org):
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg = _make_div_agg_response({"alice": [("NL", 3), ("US", 1)]})
        hit = _fake_opensearch_response(hits=[_make_hit("d1", "data.dstuser", "alice")])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg, hit]

            incident = run(diversity_rule, org)

        assert incident is not None
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1

    def test_does_not_fire_with_single_distinct_value(self, diversity_rule, org):
        """doc_count >= count but only 1 distinct country → no incident."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg = _make_div_agg_response({"alice": [("NL", 5)]})

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg]

            result = run(diversity_rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org).exists()

    def test_single_leg_diversity_uses_agg_path(self, diversity_rule, org):
        """A single-leg diversity rule routes through the agg path (agg + hit fetch), not degenerate."""
        from correlations.services.search_evaluator import run

        agg = _make_div_agg_response({"alice": [("NL", 2), ("RU", 1)]})
        hit = _fake_opensearch_response(hits=[_make_hit("d1", "data.dstuser", "alice")])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg, hit]

            run(diversity_rule, org)

        # agg call + one hit-fetch for the satisfied key == 2 (degenerate path would be 1)
        assert MockOS.return_value._search.call_count == 2

    def test_incident_names_the_spread(self, diversity_rule, org):
        from correlations.services.search_evaluator import run

        agg = _make_div_agg_response({"alice": [("NL", 3), ("US", 1), ("RU", 2)]})
        hit = _fake_opensearch_response(hits=[_make_hit("d1", "data.dstuser", "alice")])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg, hit]

            incident = run(diversity_rule, org)

        assert "alice" in incident.title
        assert "NL" in incident.title and "US" in incident.title and "RU" in incident.title
        assert "## Diversity" in incident.description
        assert "NL (3)" in incident.description


# ── Diversity Constraint — slice 2: multi-leg composition ─────────────────────

@pytest.fixture
def multi_leg_diversity_rule(org):
    """leg1: successful logins spanning ≥2 countries; leg2: a privilege-escalation event.
    Both must hold for the same user within the window."""
    r = SearchRule.objects.create(
        organization=org,
        name="Travel + PrivEsc",
        severity="critical",
        correlation_key="user.name",
        window_minutes=60,
        interval_minutes=15,
        max_findings_per_run=50,
    )
    leg1 = SearchRuleLeg.objects.create(
        rule=r, display_order=0, count=1,
        distinct_field="GeoLocation.country_name", min_distinct=2,
    )
    SearchLegCondition.objects.create(
        leg=leg1, field_name="rule.groups",
        operator=SEARCH_OPERATOR_EQUALS, value="authentication_success",
    )
    leg2 = SearchRuleLeg.objects.create(rule=r, display_order=1, count=1)
    SearchLegCondition.objects.create(
        leg=leg2, field_name="rule.groups",
        operator=SEARCH_OPERATOR_EQUALS, value="privilege_escalation",
    )
    return r


@pytest.mark.django_db
class TestMultiLegDiversityComposition:
    def test_fires_when_both_legs_satisfied(self, multi_leg_diversity_rule, org):
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg_div = _make_div_agg_response({"alice": [("NL", 2), ("US", 1)]})
        agg_plain = _make_agg_response({"alice": 1})
        hit = _fake_opensearch_response(hits=[_make_hit("d1", "data.dstuser", "alice")])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            # leg1 agg, leg2 agg, then per satisfied key: leg1 hit, leg2 hit
            MockOS.return_value._search.side_effect = [agg_div, agg_plain, hit, hit]

            incident = run(multi_leg_diversity_rule, org)

        assert incident is not None
        assert Incident.objects.filter(organization=org, source_kind="scheduled_search").count() == 1

    def test_no_fire_when_plain_leg_key_absent(self, multi_leg_diversity_rule, org):
        """Diversity leg satisfied for alice, but the plain leg only has bob → no intersection."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg_div = _make_div_agg_response({"alice": [("NL", 2), ("US", 1)]})
        agg_plain = _make_agg_response({"bob": 3})

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg_div, agg_plain]

            result = run(multi_leg_diversity_rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org).exists()

    def test_no_fire_when_diversity_fails_but_plain_present(self, multi_leg_diversity_rule, org):
        """Plain leg has alice, but the diversity leg sees only one country for alice → no fire."""
        from correlations.services.search_evaluator import run
        from incidents.models import Incident

        agg_div = _make_div_agg_response({"alice": [("NL", 5)]})
        agg_plain = _make_agg_response({"alice": 2})

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg_div, agg_plain]

            result = run(multi_leg_diversity_rule, org)

        assert result is None
        assert not Incident.objects.filter(organization=org).exists()

    def test_incident_names_spread_from_diversity_leg(self, multi_leg_diversity_rule, org):
        from correlations.services.search_evaluator import run

        agg_div = _make_div_agg_response({"alice": [("NL", 2), ("BE", 1)]})
        agg_plain = _make_agg_response({"alice": 1})
        hit = _fake_opensearch_response(hits=[_make_hit("d1", "data.dstuser", "alice")])

        with (
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
            patch(_EXTRACT_IOCS),
            patch(_ACQUIRE_LOCK, return_value=False),
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value.get_field_mapping.return_value = {}
            MockOS.return_value._search.side_effect = [agg_div, agg_plain, hit, hit]

            incident = run(multi_leg_diversity_rule, org)

        assert "## Diversity" in incident.description
        assert "NL" in incident.description and "BE" in incident.description


# ── Diversity Constraint — slice 3: serializer (manual builder) validation ─────

_DIV_SER_MAPPING = {
    "rule.groups": "keyword",
    "GeoLocation.country_name": "keyword",
    "data.dstuser": "keyword",
    "rule.description": "text",
}


@pytest.mark.django_db
class TestSearchRuleDiversityValidation:
    """SearchRule create rejects diversity constraints that violate the four invariants."""

    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("divstaff@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _payload(self, org, *, correlation_key="user.name",
                 distinct_field="GeoLocation.country_name", min_distinct=2):
        return {
            "organization": org.pk,
            "name": "Diversity Test",
            "severity": "high",
            "correlation_key": correlation_key,
            "window_minutes": 60,
            "interval_minutes": 15,
            "max_findings_per_run": 50,
            "enabled": True,
            "legs": [{
                "count": 1,
                "display_order": 0,
                "distinct_field": distinct_field,
                "min_distinct": min_distinct,
                "conditions": [{
                    "field_name": "rule.groups",
                    "operator": "equals",
                    "value": "authentication_success",
                }],
            }],
        }

    @patch("correlations.views._get_mapping_safe")
    def test_valid_diversity_rule_saves(self, mock_mapping, org):
        mock_mapping.return_value = _DIV_SER_MAPPING
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            resp = self._staff_client().post(
                "/api/correlations/search-rules/", self._payload(org), format="json"
            )
        assert resp.status_code == 201, resp.data
        assert resp.data["legs"][0]["distinct_field"] == "GeoLocation.country_name"
        assert resp.data["legs"][0]["min_distinct"] == 2

    @patch("correlations.views._get_mapping_safe")
    def test_none_key_with_diversity_rejected(self, mock_mapping, org):
        mock_mapping.return_value = _DIV_SER_MAPPING
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, correlation_key="none"), format="json",
        )
        assert resp.status_code == 400
        assert "legs" in resp.data

    @patch("correlations.views._get_mapping_safe")
    def test_min_distinct_below_two_rejected(self, mock_mapping, org):
        mock_mapping.return_value = _DIV_SER_MAPPING
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, min_distinct=1), format="json",
        )
        assert resp.status_code == 400
        assert "legs" in resp.data

    @patch("correlations.views._get_mapping_safe")
    def test_distinct_field_equal_to_key_field_rejected(self, mock_mapping, org):
        # user.name → data.dstuser; diversifying on the key field is a dead rule.
        mock_mapping.return_value = _DIV_SER_MAPPING
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, distinct_field="data.dstuser"), format="json",
        )
        assert resp.status_code == 400
        assert "legs" in resp.data

    @patch("correlations.views._get_mapping_safe")
    def test_non_aggregatable_distinct_field_rejected(self, mock_mapping, org):
        mock_mapping.return_value = _DIV_SER_MAPPING
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, distinct_field="rule.description"), format="json",
        )
        assert resp.status_code == 400
        assert "legs" in resp.data

    @patch("correlations.views._get_mapping_safe")
    def test_no_diversity_rule_unaffected(self, mock_mapping, org):
        """A leg without a distinct_field saves normally (no diversity validation)."""
        mock_mapping.return_value = _DIV_SER_MAPPING
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            resp = self._staff_client().post(
                "/api/correlations/search-rules/",
                self._payload(org, distinct_field=""), format="json",
            )
        assert resp.status_code == 201, resp.data


# ── Firing summary on the search rule list (#438) ───────────────────────────────


@pytest.mark.django_db
class TestFiringSummary:
    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("staff_fs@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_never_fired_rule_reports_null_last_fired(self, rule):
        client = self._staff_client()
        resp = client.get("/api/correlations/search-rules/")
        assert resp.status_code == 200
        row = next(r for r in resp.data if r["id"] == rule.id)
        assert row["firing_summary"]["count"] == 0
        assert row["firing_summary"]["last_fired_at"] is None

    def test_fired_rule_reports_count_and_last_fired(self, rule, org):
        SearchFiring.objects.create(rule=rule, organization=org, finding_count=1)
        latest = SearchFiring.objects.create(rule=rule, organization=org, finding_count=2)
        client = self._staff_client()
        resp = client.get("/api/correlations/search-rules/")
        row = next(r for r in resp.data if r["id"] == rule.id)
        assert row["firing_summary"]["count"] == 2
        assert row["firing_summary"]["last_fired_at"] is not None

    def test_list_firing_summary_no_n_plus_one(self, rule, org):
        """The list computes firing summaries via annotation, not per-rule queries."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        SearchFiring.objects.create(rule=rule, organization=org, finding_count=1)
        # second rule with no firings
        SearchRule.objects.create(organization=org, name="Second", window_minutes=60, interval_minutes=15)
        client = self._staff_client()
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get("/api/correlations/search-rules/")
        assert resp.status_code == 200
        # no aggregate query is issued per-rule: the firing count/last-fired join is annotated.
        firing_qs = [q["sql"] for q in ctx.captured_queries if "firings" in q["sql"].lower() or "searchfiring" in q["sql"].lower()]
        assert len(firing_qs) <= 1


# ── Spec-based debug run on unsaved rule spec (#437) ────────────────────────────


@pytest.mark.django_db
class TestSpecDebug:
    _URL = "/api/correlations/search-rules/debug/"

    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("staff_sd@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _spec(self, org, **overrides):
        spec = {
            "org_slug": org.slug,
            "name": "Unsaved rule",
            "severity": "high",
            "correlation_key": "none",
            "window_minutes": 60,
            "interval_minutes": 15,
            "max_findings_per_run": 50,
            "include_agentless": False,
            "organization": org.id,
            "legs": [
                {
                    "count": 1,
                    "display_order": 0,
                    "conditions": [
                        {"field_name": "rule.description", "operator": "contains", "value": "brute force"},
                    ],
                }
            ],
        }
        spec.update(overrides)
        return spec

    def test_requires_staff(self, org, django_user_model):
        from rest_framework.test import APIClient
        user = django_user_model.objects.create_user("plain_sd", password="x", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.post(self._URL, self._spec(org), format="json")
        assert resp.status_code in (401, 403)

    def test_returns_same_structure_and_persists_nothing(self, org):
        from correlations.models import SearchRule, SearchRuleLeg, SearchFinding, SearchFiring
        from alerts.models import Alert
        from incidents.models import Incident

        with (
            patch("correlations.views._get_mapping_safe", return_value=_DIV_SER_MAPPING),
            patch(_WAZUH_CLIENT) as MockWazuh,
            patch(_OS_CLIENT) as MockOS,
        ):
            MockWazuh.return_value.get_agents.return_value = _FAKE_AGENTS
            MockOS.return_value._search.return_value = _fake_opensearch_response()
            resp = self._staff_client().post(self._URL, self._spec(org), format="json")

        assert resp.status_code == 200, resp.data
        body = resp.data
        assert body["mode"] == "single"
        assert "legs" in body
        assert body["legs"][0]["hit_query"]
        # Nothing persisted.
        assert SearchRule.objects.count() == 0
        assert SearchRuleLeg.objects.count() == 0
        assert SearchFinding.objects.count() == 0
        assert SearchFiring.objects.count() == 0
        assert Alert.objects.count() == 0
        assert Incident.objects.count() == 0

    def test_invalid_spec_returns_validation_error(self, org):
        spec = self._spec(org)
        spec["legs"] = []  # at least one leg required by serializer? empty legs -> debug error or 400
        spec["window_minutes"] = "not-a-number"
        resp = self._staff_client().post(self._URL, spec, format="json")
        assert resp.status_code == 400

    def test_missing_org_slug_rejected(self, org):
        spec = self._spec(org)
        del spec["org_slug"]
        resp = self._staff_client().post(self._URL, spec, format="json")
        assert resp.status_code == 400


# ── Time-of-day window (#440) ───────────────────────────────────────────────────


from datetime import time as _dtime


@pytest.mark.django_db
class TestTimeOfDayWindowCompiler:
    def _rule(self, org, **kw):
        defaults = dict(
            organization=org, name="tw", window_minutes=60, interval_minutes=15,
            time_window_start=_dtime(8, 0), time_window_end=_dtime(18, 0),
            time_window_days=[1, 2, 3, 4, 5], time_window_mode="inside",
        )
        defaults.update(kw)
        return SearchRule.objects.create(**defaults)

    def test_no_window_returns_none(self, org):
        from correlations.services.search_compiler import build_time_of_day_filter
        rule = SearchRule.objects.create(organization=org, name="nw", window_minutes=60, interval_minutes=15)
        assert build_time_of_day_filter(rule, org.timezone) is None

    def test_inside_window_builds_script_filter(self, org):
        from correlations.services.search_compiler import build_time_of_day_filter
        rule = self._rule(org, time_window_mode="inside")
        clause = build_time_of_day_filter(rule, "Europe/Amsterdam")
        assert "script" in clause
        params = clause["script"]["script"]["params"]
        assert params["tz"] == "Europe/Amsterdam"
        assert params["days"] == [1, 2, 3, 4, 5]
        assert params["start"] == 8 * 60
        assert params["end"] == 18 * 60
        assert params["inside"] is True

    def test_outside_mode_flips_inside_flag(self, org):
        from correlations.services.search_compiler import build_time_of_day_filter
        rule = self._rule(org, time_window_mode="outside")
        clause = build_time_of_day_filter(rule, org.timezone)
        assert clause["script"]["script"]["params"]["inside"] is False

    def test_cross_midnight_window_uses_or_branch(self, org):
        from correlations.services.search_compiler import build_time_of_day_filter
        rule = self._rule(org, time_window_start=_dtime(22, 0), time_window_end=_dtime(6, 0))
        clause = build_time_of_day_filter(rule, org.timezone)
        params = clause["script"]["script"]["params"]
        assert params["start"] == 22 * 60
        assert params["end"] == 6 * 60
        # the painless source must handle start > end (the OR branch)
        assert "m >= params.start || m < params.end" in clause["script"]["script"]["source"]

    def test_filter_is_appended_to_compiled_query(self, org):
        from correlations.services.search_compiler import build_time_of_day_filter, compile_query
        rule = self._rule(org)
        clause = build_time_of_day_filter(rule, org.timezone)
        body = compile_query([], ["001"], timezone.now(), timezone.now(), 10, extra_filters=[clause])
        assert clause in body["query"]["bool"]["filter"]


@pytest.mark.django_db
class TestTimeOfDayWindowSerializer:
    def _staff_client(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        user = User.objects.create_user("staff_tw@test.com", password="x", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _payload(self, org, **overrides):
        p = {
            "name": "tw rule", "severity": "high", "correlation_key": "none",
            "window_minutes": 60, "interval_minutes": 15, "max_findings_per_run": 50,
            "organization": org.id,
            "legs": [{"count": 1, "display_order": 0, "conditions": []}],
        }
        p.update(overrides)
        return p

    def test_valid_window_saves(self, org):
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            resp = self._staff_client().post(
                "/api/correlations/search-rules/",
                self._payload(
                    org,
                    time_window_start="08:00:00", time_window_end="18:00:00",
                    time_window_days=[1, 2, 3, 4, 5], time_window_mode="outside",
                ),
                format="json",
            )
        assert resp.status_code == 201, resp.data
        rule = SearchRule.objects.get(pk=resp.data["id"])
        assert rule.has_time_window
        assert rule.time_window_mode == "outside"

    def test_start_without_end_rejected(self, org):
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, time_window_start="08:00:00", time_window_days=[1]),
            format="json",
        )
        assert resp.status_code == 400
        assert "time_window_start" in resp.data

    def test_window_without_days_rejected(self, org):
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, time_window_start="08:00:00", time_window_end="18:00:00", time_window_days=[]),
            format="json",
        )
        assert resp.status_code == 400
        assert "time_window_days" in resp.data

    def test_invalid_day_value_rejected(self, org):
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, time_window_start="08:00:00", time_window_end="18:00:00", time_window_days=[9]),
            format="json",
        )
        assert resp.status_code == 400

    def test_equal_start_end_rejected(self, org):
        resp = self._staff_client().post(
            "/api/correlations/search-rules/",
            self._payload(org, time_window_start="08:00:00", time_window_end="08:00:00", time_window_days=[1]),
            format="json",
        )
        assert resp.status_code == 400
        assert "time_window_end" in resp.data

    def test_no_window_unaffected(self, org):
        with patch("correlations.services.search_schedule.sync_rule_schedule"):
            resp = self._staff_client().post(
                "/api/correlations/search-rules/", self._payload(org), format="json",
            )
        assert resp.status_code == 201, resp.data
        rule = SearchRule.objects.get(pk=resp.data["id"])
        assert rule.has_time_window is False
