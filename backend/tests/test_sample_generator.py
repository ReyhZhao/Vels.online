"""Tests for the LLM Sample Document generator (PRD #439 slice 5).

Covers grounding construction (stubbed OpenSearch), the mapping-aware sanitiser, and
the generate endpoint with a stubbed provider. Nothing is persisted or run.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from correlations.llm.sample_generator import (
    build_sample_grounding,
    generate_samples,
    sanitize_sample_docs,
)
from correlations.models import (
    SEARCH_OPERATOR_EQUALS,
    SearchLegCondition,
    SearchRule,
    SearchRuleLeg,
    SearchRuleTest,
)
from security.models import Organization

_OS_CLIENT = "security.opensearch.OpenSearchClient"
_PROVIDER = "correlations.llm.factory.get_draft_provider"
_GEN_PROVIDER = "correlations.llm.factory.get_draft_provider"


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="GenTest", slug="gentest", wazuh_group="gentest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


@pytest.fixture
def rule(org):
    r = SearchRule.objects.create(
        organization=org, name="BF", severity="high", correlation_key="host.name",
        window_minutes=30, interval_minutes=15, max_findings_per_run=50,
    )
    leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=3)
    SearchLegCondition.objects.create(leg=leg, field_name="rule.id", operator=SEARCH_OPERATOR_EQUALS, value="5710")
    return r


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff_gen", password="p", is_staff=True)


# ── Sanitiser ────────────────────────────────────────────────────────────────

class TestSanitizer:
    _MAPPING = {"rule.id": "keyword", "@timestamp": "date", "agent.name": "keyword"}

    def test_drops_unknown_fields_and_warns(self):
        docs = [{"@timestamp": "2026-06-06T10:00:00Z", "rule": {"id": "5710"}, "bogus": {"x": 1}}]
        clean, warnings = sanitize_sample_docs(docs, self._MAPPING)
        assert clean == [{"@timestamp": "2026-06-06T10:00:00Z", "rule": {"id": "5710"}}]
        assert any("bogus" in w for w in warnings)

    def test_drops_doc_without_timestamp(self):
        docs = [{"rule": {"id": "5710"}}]
        clean, warnings = sanitize_sample_docs(docs, self._MAPPING)
        assert clean == []
        assert any("@timestamp" in w for w in warnings)

    def test_drops_non_object_doc(self):
        clean, warnings = sanitize_sample_docs(["nope"], self._MAPPING)
        assert clean == []
        assert any("not a JSON object" in w for w in warnings)

    def test_empty_mapping_keeps_all_fields(self):
        docs = [{"@timestamp": "2026-06-06T10:00:00Z", "anything": {"goes": 1}}]
        clean, warnings = sanitize_sample_docs(docs, {})
        assert clean == docs


# ── Grounding ────────────────────────────────────────────────────────────────

class TestGrounding:
    def test_grounding_includes_rule_and_sample_docs(self, rule):
        m = MagicMock()
        m.get_field_mapping.return_value = {"rule.id": "keyword"}
        m.get_rule_catalog.return_value = {}
        m.get_sample_docs.return_value = [{"rule": {"id": "5710"}}]
        with patch(_OS_CLIENT, return_value=m):
            grounding = build_sample_grounding(rule)

        assert grounding["rule"]["name"] == "BF"
        assert grounding["rule"]["legs"][0]["count"] == 3
        assert grounding["sample_docs"] == [{"rule": {"id": "5710"}}]
        # The rule's referenced rule.id is passed to get_sample_docs for realistic grounding.
        assert m.get_sample_docs.call_args.kwargs["rule_ids"] == ["5710"]


# ── End-to-end generate (stubbed provider) ───────────────────────────────────

class TestGenerateSamples:
    def test_generates_and_sanitises(self, rule):
        m = MagicMock()
        m.get_field_mapping.return_value = {"rule.id": "keyword", "@timestamp": "date"}
        m.get_rule_catalog.return_value = {}
        m.get_sample_docs.return_value = []
        provider = MagicMock()
        provider.generate_sample_docs.return_value = [
            {"@timestamp": "2026-06-06T10:00:00Z", "rule": {"id": "5710"}, "ghost": 1},
        ]
        with patch(_OS_CLIENT, return_value=m), patch(_GEN_PROVIDER, return_value=provider):
            result = generate_samples(rule, expect_fire=True)

        assert result["samples"] == [{"@timestamp": "2026-06-06T10:00:00Z", "rule": {"id": "5710"}}]
        assert any("ghost" in w for w in result["warnings"])
        provider.generate_sample_docs.assert_called_once()
        # expect_fire forwarded to the provider.
        assert provider.generate_sample_docs.call_args[0][1] is True


# ── Endpoint ─────────────────────────────────────────────────────────────────

class TestGenerateEndpoint:
    _BASE = "/api/correlations/search-rules"

    def test_requires_staff(self, client, db, rule, django_user_model):
        u = django_user_model.objects.create_user(username="nu", password="p", is_staff=False)
        client.force_login(u)
        r = client.post(f"{self._BASE}/{rule.id}/tests/generate/", content_type="application/json")
        assert r.status_code == 403

    def test_returns_candidates_without_persisting(self, client, staff, rule):
        client.force_login(staff)
        m = MagicMock()
        m.get_field_mapping.return_value = {"rule.id": "keyword", "@timestamp": "date"}
        m.get_rule_catalog.return_value = {}
        m.get_sample_docs.return_value = []
        provider = MagicMock()
        provider.generate_sample_docs.return_value = [{"@timestamp": "2026-06-06T10:00:00Z", "rule": {"id": "5710"}}]
        with patch(_OS_CLIENT, return_value=m), patch(_GEN_PROVIDER, return_value=provider):
            r = client.post(
                f"{self._BASE}/{rule.id}/tests/generate/",
                data=json.dumps({"expect_fire": True}),
                content_type="application/json",
            )
        assert r.status_code == 200
        assert len(r.json()["samples"]) == 1
        # Generation never persists a test.
        assert SearchRuleTest.objects.count() == 0

    def test_provider_unavailable_returns_503(self, client, staff, rule):
        from correlations.llm.base import DraftConfigError
        client.force_login(staff)
        m = MagicMock()
        m.get_field_mapping.return_value = {}
        m.get_rule_catalog.return_value = {}
        m.get_sample_docs.return_value = []
        with patch(_OS_CLIENT, return_value=m), patch(_GEN_PROVIDER, side_effect=DraftConfigError("no key")):
            r = client.post(
                f"{self._BASE}/{rule.id}/tests/generate/",
                data=json.dumps({"expect_fire": True}),
                content_type="application/json",
            )
        assert r.status_code == 503
