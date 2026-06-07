"""Tests for Rule Tests — end-to-end (PRD #439 slice 2, ADR-0010).

Covers the sandbox harness (OpenSearch stubbed at the boundary), the pure verdict
builder, and the staff-only CRUD + run API. A test run must create no production
side effects (Incident/Alert/SearchFiring/SearchFinding).
"""
import json
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
    SearchRuleTest,
)
from correlations.services.search_evaluator import Decision
from correlations.services.search_test_runner import (
    TEST_INDEX_PREFIX,
    build_verdict,
    run_rule_test,
)
from incidents.models import Incident
from security.models import Organization

_OS_CLIENT = "security.opensearch.OpenSearchClient"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="RTTest", slug="rttest", wazuh_group="rttest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


@pytest.fixture
def rule(org):
    r = SearchRule.objects.create(
        organization=org, name="Brute Force", severity="high",
        correlation_key="none", window_minutes=60, interval_minutes=15,
        max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1)
    SearchLegCondition.objects.create(
        leg=leg, field_name="rule.description", operator=SEARCH_OPERATOR_CONTAINS, value="brute force",
    )
    return r


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff_rt", password="p", is_staff=True)


@pytest.fixture
def non_staff(db, django_user_model):
    return django_user_model.objects.create_user(username="user_rt", password="p", is_staff=False)


def _sample(ts="2026-06-06T10:00:00Z", desc="brute force"):
    return {"@timestamp": ts, "rule": {"description": desc}}


def _os_mock(hits):
    """A MagicMock OpenSearchClient whose _search returns the given hits."""
    m = MagicMock()
    m.get_raw_mapping.return_value = {"properties": {"rule": {"properties": {"description": {"type": "text"}}}}}
    m._search.return_value = {"hits": {"hits": hits, "total": {"value": len(hits)}}}
    return m


# ── Verdict builder (pure) ───────────────────────────────────────────────────

class TestVerdictBuilder:
    def test_should_fire_and_fires_passes(self):
        d = Decision(True, [object()], {"mode": "single"})
        v = build_verdict(True, d)
        assert v["status"] == "pass" and v["passed"] is True and v["fired"] is True

    def test_should_fire_but_does_not_fails(self):
        d = Decision(False, [], {"mode": "single"})
        v = build_verdict(True, d)
        assert v["status"] == "fail" and v["passed"] is False and v["fired"] is False

    def test_should_not_fire_but_fires_fails(self):
        d = Decision(True, [object()], {})
        v = build_verdict(False, d)
        assert v["status"] == "fail" and v["passed"] is False

    def test_should_not_fire_and_does_not_passes(self):
        d = Decision(False, [], {})
        v = build_verdict(False, d)
        assert v["status"] == "pass" and v["passed"] is True


# ── Sandbox harness ──────────────────────────────────────────────────────────

class TestSandboxHarness:
    def test_lifecycle_create_load_refresh_drop(self, rule):
        m = _os_mock([{"_id": "d1", "_source": _sample()}])
        with patch(_OS_CLIENT, return_value=m):
            result = run_rule_test(rule, [_sample()], expect_fire=True)

        assert result["status"] == "pass"
        # Index created with cloned mapping, named non-glob, loaded, refreshed, dropped.
        created_index = m.create_index.call_args[0][0]
        assert created_index.startswith(TEST_INDEX_PREFIX)
        assert "wazuh-alerts" not in created_index
        assert m.create_index.call_args.kwargs["mappings"] == m.get_raw_mapping.return_value
        m.bulk_index.assert_called_once()
        m.refresh.assert_called_once()
        m.delete_index.assert_called_once_with(created_index)

    def test_index_dropped_even_on_error(self, rule):
        from security.opensearch import OpenSearchError
        m = _os_mock([])
        m._search.side_effect = OpenSearchError("boom")
        with patch(_OS_CLIENT, return_value=m):
            result = run_rule_test(rule, [_sample()], expect_fire=True)

        assert result["status"] == "error"
        m.delete_index.assert_called_once()  # finally still drops the index

    def test_scope_neutralised_no_agent_filter(self, rule):
        m = _os_mock([{"_id": "d1", "_source": _sample()}])
        with patch(_OS_CLIENT, return_value=m):
            run_rule_test(rule, [_sample()], expect_fire=True)

        body = m._search.call_args[0][1]
        filters = body["query"]["bool"]["filter"]
        assert not any("agent.id" in (f.get("terms") or {}) for f in filters)

    def test_window_anchored_to_latest_sample(self, rule):
        m = _os_mock([{"_id": "d1", "_source": _sample()}])
        samples = [_sample(ts="2020-01-01T00:00:00Z"), _sample(ts="2020-01-01T00:30:00Z")]
        with patch(_OS_CLIENT, return_value=m):
            run_rule_test(rule, samples, expect_fire=True)

        body = m._search.call_args[0][1]
        ranges = [f["range"]["@timestamp"] for f in body["query"]["bool"]["filter"] if "range" in f]
        assert ranges and ranges[0]["lte"].startswith("2020-01-01T00:30:00")

    def test_too_many_samples_errors(self, rule):
        from correlations.services.search_test_runner import MAX_SAMPLES_PER_TEST
        result = run_rule_test(rule, [_sample()] * (MAX_SAMPLES_PER_TEST + 1), expect_fire=True)
        assert result["status"] == "error"


# ── API ──────────────────────────────────────────────────────────────────────

_BASE = "/api/correlations/search-rules"


class TestRuleTestAPI:
    def test_crud_requires_staff(self, client, non_staff, rule):
        client.force_login(non_staff)
        r = client.get(f"{_BASE}/{rule.id}/tests/")
        assert r.status_code == 403

    def test_create_and_list(self, client, staff, rule):
        client.force_login(staff)
        r = client.post(
            f"{_BASE}/{rule.id}/tests/",
            data=json.dumps({"name": "TP", "expect_fire": True, "samples": [_sample()]}),
            content_type="application/json",
        )
        assert r.status_code == 201
        assert r.json()["last_status"] == "never"
        lst = client.get(f"{_BASE}/{rule.id}/tests/")
        assert len(lst.json()) == 1

    def test_create_rejects_non_object_samples(self, client, staff, rule):
        client.force_login(staff)
        r = client.post(
            f"{_BASE}/{rule.id}/tests/",
            data=json.dumps({"name": "bad", "expect_fire": True, "samples": ["not a dict"]}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_run_persists_summary_and_no_side_effects(self, client, staff, rule, org):
        test = SearchRuleTest.objects.create(
            rule=rule, name="TP", expect_fire=True, samples=[_sample()],
        )
        client.force_login(staff)
        m = _os_mock([{"_id": "d1", "_source": _sample()}])
        with patch(_OS_CLIENT, return_value=m):
            r = client.post(f"{_BASE}/{rule.id}/tests/{test.id}/run/")

        assert r.status_code == 200
        assert r.json()["status"] == "pass"
        test.refresh_from_db()
        assert test.last_status == "pass"
        assert test.last_run_at is not None
        # Zero production side effects.
        assert Alert.objects.count() == 0
        assert Incident.objects.count() == 0
        assert SearchFiring.objects.count() == 0
        assert SearchFinding.objects.count() == 0

    def test_delete(self, client, staff, rule):
        test = SearchRuleTest.objects.create(rule=rule, name="x", expect_fire=True, samples=[])
        client.force_login(staff)
        r = client.delete(f"{_BASE}/{rule.id}/tests/{test.id}/")
        assert r.status_code == 204
        assert not SearchRuleTest.objects.filter(id=test.id).exists()
