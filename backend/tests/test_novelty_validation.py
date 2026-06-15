"""Novelty Constraint — schema validation + serializer round-trip (#522, ADR-0021).

A Novelty Constraint fires the *first time* a value of a leg's novelty_field is seen for a
correlation key — e.g. "a user logged onto a host new for them" (correlation_key=user.name,
novelty_field=agent.name). This module covers validate_novelty_constraint and the serializer
guards + round-trip; evaluation lives in test_novelty_decide.py.
"""
from unittest.mock import patch

import pytest

from correlations.models import SEARCH_COUNT_OP_GTE, SEARCH_COUNT_OP_LTE
from security.models import Organization


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="NoveltyTest", slug="noveltytest", wazuh_group="noveltytest",
        alert_match_lookback_days=30, alert_auto_promote_threshold=5,
        alert_auto_promote_window_minutes=60,
    )


# A mapping where the canonical login fields are aggregatable keyword and the user field is
# text (so .keyword resolution / non-aggregatable checks can be exercised).
_MAPPING = {
    "agent.name": "keyword",
    "data.dstuser": "keyword",
    "rule.description": "text",
}


class TestValidateNoveltyConstraint:
    def _check(self, novelty_field, key="user.name", op=SEARCH_COUNT_OP_GTE, mapping=None):
        from correlations.services.search_compiler import validate_novelty_constraint
        return validate_novelty_constraint(novelty_field, key, op, mapping or {})

    def test_empty_novelty_field_is_valid(self):
        ok, reason = self._check("")
        assert ok and reason == ""

    def test_none_correlation_key_rejected(self):
        ok, reason = self._check("agent.name", key="none")
        assert not ok
        assert "correlation key" in reason

    def test_lte_count_operator_rejected(self):
        ok, reason = self._check("agent.name", op=SEARCH_COUNT_OP_LTE)
        assert not ok
        assert "incoherent" in reason.lower()

    def test_novelty_field_equal_to_key_field_rejected(self):
        # user.name maps to data.dstuser; novelty on data.dstuser is self-novelty.
        ok, reason = self._check("data.dstuser", key="user.name")
        assert not ok
        assert "differ" in reason

    def test_non_aggregatable_field_rejected(self):
        ok, reason = self._check("rule.description", mapping=_MAPPING)
        assert not ok
        assert "non-aggregatable" in reason

    def test_missing_field_rejected(self):
        ok, reason = self._check("data.nope", mapping=_MAPPING)
        assert not ok
        assert "does not exist" in reason

    def test_valid_novelty_field_passes(self):
        ok, reason = self._check("agent.name", key="user.name", mapping=_MAPPING)
        assert ok, reason


class TestNoveltySerializer:
    def _payload(self, correlation_key="user.name", novelty_field="agent.name",
                 count_operator=SEARCH_COUNT_OP_GTE, baseline_lookback_days=30):
        return {
            "name": "first logon", "severity": "high",
            "correlation_key": correlation_key,
            "window_minutes": 60, "interval_minutes": 15,
            "baseline_lookback_days": baseline_lookback_days,
            "legs": [{
                "count": 1, "count_operator": count_operator, "display_order": 0,
                "novelty_field": novelty_field,
                "conditions": [{
                    "field_name": "rule.description", "operator": "contains",
                    "value": "authentication success",
                }],
            }],
        }

    @pytest.mark.django_db
    def test_valid_novelty_rule_accepted_and_round_trips(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value=_MAPPING):
            ser = _SearchRuleSerializer(data=self._payload())
            assert ser.is_valid(), ser.errors
            rule = ser.save()
        rule.refresh_from_db()
        assert rule.baseline_lookback_days == 30
        leg = rule.legs.first()
        assert leg.novelty_field == "agent.name"
        assert leg.has_novelty is True
        data = _SearchRuleSerializer(rule).data
        assert data["baseline_lookback_days"] == 30
        assert data["legs"][0]["novelty_field"] == "agent.name"

    @pytest.mark.django_db
    def test_novelty_with_none_key_rejected(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value=_MAPPING):
            ser = _SearchRuleSerializer(data=self._payload(correlation_key="none"))
            assert not ser.is_valid()
        assert "legs" in ser.errors

    @pytest.mark.django_db
    def test_novelty_with_lte_rejected(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value=_MAPPING):
            ser = _SearchRuleSerializer(data=self._payload(count_operator=SEARCH_COUNT_OP_LTE))
            assert not ser.is_valid()
        assert "legs" in ser.errors

    @pytest.mark.django_db
    def test_non_aggregatable_novelty_field_rejected(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value=_MAPPING):
            ser = _SearchRuleSerializer(data=self._payload(novelty_field="rule.description"))
            assert not ser.is_valid()
        assert "legs" in ser.errors

    @pytest.mark.django_db
    def test_ordinary_rule_without_novelty_unaffected(self):
        from correlations.views import _SearchRuleSerializer
        with patch("correlations.views._get_mapping_safe", return_value=_MAPPING):
            ser = _SearchRuleSerializer(data=self._payload(novelty_field=""))
            assert ser.is_valid(), ser.errors
