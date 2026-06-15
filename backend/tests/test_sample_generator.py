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


# ── Novelty / absence-aware prompt (#521, ADR-0021) ──────────────────────────

class TestSampleGenPromptNovelty:
    def _novelty_rule(self, org):
        r = SearchRule.objects.create(
            organization=org, name="first logon", severity="high", correlation_key="user.name",
            window_minutes=60, interval_minutes=15, baseline_lookback_days=90, max_findings_per_run=50,
        )
        leg = SearchRuleLeg.objects.create(rule=r, display_order=0, count=1, novelty_field="agent.name")
        SearchLegCondition.objects.create(
            leg=leg, field_name="rule.id", operator=SEARCH_OPERATOR_EQUALS, value="5715",
        )
        return r

    @pytest.mark.django_db
    def test_summarize_includes_novelty_and_baseline(self, org):
        from correlations.llm.sample_generator import _summarize_rule
        summary = _summarize_rule(self._novelty_rule(org))
        assert summary["baseline_lookback_days"] == 90
        assert summary["interval_minutes"] == 15
        assert summary["legs"][0]["novelty_field"] == "agent.name"

    @pytest.mark.django_db
    def test_should_fire_prompt_stages_baseline_and_new_value(self, org):
        from correlations.llm.sample_generator import _summarize_rule
        from correlations.llm.search_prompt import build_sample_gen_prompt
        grounding = {"rule": _summarize_rule(self._novelty_rule(org)), "core_fields": [], "sample_docs": []}
        prompt = build_sample_gen_prompt(grounding, expect_fire=True)
        assert "agent.name" in prompt
        assert "now-" in prompt  # relative offsets
        assert "BRAND NEW" in prompt
        assert "BASELINE" in prompt

    @pytest.mark.django_db
    def test_should_not_fire_prompt_uses_known_value(self, org):
        from correlations.llm.sample_generator import _summarize_rule
        from correlations.llm.search_prompt import build_sample_gen_prompt
        grounding = {"rule": _summarize_rule(self._novelty_rule(org)), "core_fields": [], "sample_docs": []}
        prompt = build_sample_gen_prompt(grounding, expect_fire=False)
        assert "KNOWN" in prompt
        assert "now-" in prompt

    def test_absence_should_fire_prompt_asks_for_no_matches(self):
        from correlations.llm.search_prompt import build_sample_gen_prompt
        rule = {"window_minutes": 60, "interval_minutes": 15, "baseline_lookback_days": 30,
                "legs": [{"count": 0, "count_operator": "lte", "novelty_field": None}]}
        prompt = build_sample_gen_prompt({"rule": rule, "core_fields": [], "sample_docs": []}, expect_fire=True)
        assert "ABSENCE" in prompt
        assert "NO documents" in prompt

    def test_plain_count_rule_keeps_single_window_guidance(self):
        from correlations.llm.search_prompt import build_sample_gen_prompt
        rule = {"window_minutes": 30, "interval_minutes": 15, "baseline_lookback_days": 30,
                "legs": [{"count": 3, "count_operator": "gte", "novelty_field": None}]}
        prompt = build_sample_gen_prompt({"rule": rule, "core_fields": [], "sample_docs": []}, expect_fire=True)
        assert "30 minutes of each other" in prompt
        assert "BASELINE" not in prompt


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
