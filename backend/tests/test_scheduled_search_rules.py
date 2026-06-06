"""Tests for the Scheduled Search Rules walking skeleton.

Covers (external behaviour, stubbed OpenSearch/Wazuh):
- Compiler: operator → DSL for each supported operator + agent scoping + window bound
- Materialiser: idempotency + source_kind
- Evaluator: single-leg fire creating a linked Incident with source_kind=scheduled_search
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

from correlations.models import (
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
from correlations.services.search_compiler import compile_query, _condition_to_clause
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
