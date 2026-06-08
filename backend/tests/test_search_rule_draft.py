"""Tests for Scheduled Search Rule author assistant — slice 7.

Covers (per acceptance criteria):
- build_search_grounding: payload shape, catalog capping, empty-OS fallback
- Two-pass flow: pass 1 selects rule.ids, expand_rule_fields, pass 2 drafts
- sanitize_search_draft: drops fields absent from mapping, drops operator/type mismatches,
  coerces numeric fields, keeps valid conditions, never persists/activates
- SearchRuleDraftView endpoint: auth, response shape, scope injection, two-pass orchestration,
  provider unavailable, provider error
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from correlations.llm.base import RuleDraftResult
from correlations.llm.search_grounding import build_search_grounding, expand_rule_fields
from correlations.llm.search_sanitizer import sanitize_search_draft


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stub_mapping():
    return {
        "rule.id": "keyword",
        "rule.level": "long",
        "agent.name": "keyword",
        "data.srcip": "ip",
        "rule.description": "text",
    }


def _valid_search_draft():
    return {
        "name": "High-severity brute force",
        "description": "Repeated auth failures",
        "correlation_key": "host.name",
        "severity": "high",
        "window_minutes": 30,
        "interval_minutes": 15,
        "max_findings_per_run": 50,
        "enabled": True,
        "legs": [
            {
                "count": 5,
                "display_order": 0,
                "conditions": [
                    {"field_name": "rule.id", "operator": "equals", "value": "5710"},
                    {"field_name": "rule.level", "operator": "gte", "value": "8"},
                ],
            }
        ],
    }


# ── build_search_grounding ──────────────────────────────────────────────────────

_STUB_CATALOG = {
    "5710": {"description": "SSH brute force", "groups": ["sshd", "authentication"],
             "level": 10, "seen_count": 450},
    "18152": {"description": "Windows login failure", "groups": ["windows", "authentication"],
              "level": 5, "seen_count": 200},
}

_STUB_MAPPING = {
    "rule.id": "keyword",
    "rule.level": "long",
    "agent.name": "keyword",
}

# OpenSearchClient is imported lazily inside grounding functions, so patch at source.
_OS_CLIENT = "security.opensearch.OpenSearchClient"


@patch(_OS_CLIENT)
def test_grounding_has_rule_catalog(mock_cls):
    client = MagicMock()
    client.get_field_mapping.return_value = _STUB_MAPPING
    client.get_rule_catalog.return_value = _STUB_CATALOG
    mock_cls.return_value = client
    g = build_search_grounding()
    assert "rule_catalog" in g
    assert "5710" in g["rule_catalog"]


@patch(_OS_CLIENT)
def test_grounding_has_mapping(mock_cls):
    client = MagicMock()
    client.get_field_mapping.return_value = _STUB_MAPPING
    client.get_rule_catalog.return_value = {}
    mock_cls.return_value = client
    g = build_search_grounding()
    assert "mapping" in g
    assert "rule.id" in g["mapping"]


@patch(_OS_CLIENT)
def test_grounding_has_core_fields(mock_cls):
    client = MagicMock()
    client.get_field_mapping.return_value = {}
    client.get_rule_catalog.return_value = {}
    mock_cls.return_value = client
    g = build_search_grounding()
    core_names = [f["value"] for f in g["core_fields"]]
    assert "rule.id" in core_names
    assert "agent.name" in core_names
    assert "data.srcip" in core_names


@patch(_OS_CLIENT)
def test_grounding_has_correlation_keys(mock_cls):
    client = MagicMock()
    client.get_field_mapping.return_value = {}
    client.get_rule_catalog.return_value = {}
    mock_cls.return_value = client
    g = build_search_grounding()
    keys = [ck["value"] for ck in g["correlation_keys"]]
    assert "none" in keys
    assert "host.name" in keys


@patch(_OS_CLIENT)
def test_grounding_catalog_capped_at_200(mock_cls):
    large_catalog = {str(i): {"description": f"rule {i}", "groups": [], "level": 5, "seen_count": i}
                     for i in range(300)}
    client = MagicMock()
    client.get_field_mapping.return_value = {}
    client.get_rule_catalog.return_value = large_catalog
    mock_cls.return_value = client
    g = build_search_grounding()
    assert len(g["rule_catalog"]) == 200


@patch(_OS_CLIENT)
def test_grounding_opensearch_error_returns_empty(mock_cls):
    from security.opensearch import OpenSearchError
    client = MagicMock()
    client.get_field_mapping.side_effect = OpenSearchError("down")
    client.get_rule_catalog.side_effect = OpenSearchError("down")
    mock_cls.return_value = client
    g = build_search_grounding()
    assert g["rule_catalog"] == {}
    assert g["mapping"] == {}
    assert g["expanded_fields"] == {}


@patch(_OS_CLIENT)
def test_expand_rule_fields_calls_get_fields(mock_cls):
    client = MagicMock()
    client.get_fields_for_rules.return_value = {
        "rule.id": {"type": "keyword", "top_values": ["5710"], "operators": ["equals", "contains"]},
    }
    mock_cls.return_value = client
    result = expand_rule_fields(["5710"], mapping=_STUB_MAPPING)
    assert "rule.id" in result
    client.get_fields_for_rules.assert_called_once()


@patch(_OS_CLIENT)
def test_expand_rule_fields_empty_ids_returns_empty(mock_cls):
    mock_cls.return_value = MagicMock()
    result = expand_rule_fields([])
    assert result == {}
    mock_cls.return_value.get_fields_for_rules.assert_not_called()


# ── sanitize_search_draft ──────────────────────────────────────────────────────

def test_sanitizer_valid_draft_passes_through():
    draft = _valid_search_draft()
    mapping = _stub_mapping()
    sanitized, warnings = sanitize_search_draft(draft, mapping)
    assert sanitized["name"] == "High-severity brute force"
    assert len(sanitized["legs"]) == 1
    assert len(sanitized["legs"][0]["conditions"]) == 2
    assert warnings == []


def test_sanitizer_drops_field_absent_from_mapping():
    draft = _valid_search_draft()
    draft["legs"][0]["conditions"].append(
        {"field_name": "nonexistent.field", "operator": "equals", "value": "foo"}
    )
    mapping = _stub_mapping()
    sanitized, warnings = sanitize_search_draft(draft, mapping)
    cond_names = [c["field_name"] for c in sanitized["legs"][0]["conditions"]]
    assert "nonexistent.field" not in cond_names
    assert any("nonexistent.field" in w for w in warnings)


def test_sanitizer_drops_operator_type_mismatch():
    draft = _valid_search_draft()
    # cidr is not valid for keyword fields
    draft["legs"][0]["conditions"] = [
        {"field_name": "rule.id", "operator": "cidr", "value": "192.168.0.0/24"}
    ]
    mapping = _stub_mapping()
    sanitized, warnings = sanitize_search_draft(draft, mapping)
    assert sanitized["legs"][0]["conditions"] == []
    assert any("cidr" in w for w in warnings)


def test_sanitizer_allows_cidr_for_ip_field():
    draft = _valid_search_draft()
    draft["legs"][0]["conditions"] = [
        {"field_name": "data.srcip", "operator": "cidr", "value": "10.0.0.0/8"}
    ]
    mapping = _stub_mapping()
    sanitized, warnings = sanitize_search_draft(draft, mapping)
    assert len(sanitized["legs"][0]["conditions"]) == 1
    assert warnings == []


def test_sanitizer_allows_gte_for_long_field():
    draft = _valid_search_draft()
    draft["legs"][0]["conditions"] = [
        {"field_name": "rule.level", "operator": "gte", "value": "10"}
    ]
    mapping = _stub_mapping()
    sanitized, warnings = sanitize_search_draft(draft, mapping)
    assert len(sanitized["legs"][0]["conditions"]) == 1
    assert warnings == []


def test_sanitizer_bypasses_field_check_when_mapping_empty():
    draft = _valid_search_draft()
    sanitized, warnings = sanitize_search_draft(draft, {})
    assert len(sanitized["legs"][0]["conditions"]) == 2
    assert warnings == []


def test_sanitizer_invalid_correlation_key_defaults_to_none():
    draft = _valid_search_draft()
    draft["correlation_key"] = "not.valid"
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["correlation_key"] == "none"
    assert any("correlation key" in w.lower() for w in warnings)


def test_sanitizer_invalid_severity_defaults_to_medium():
    draft = _valid_search_draft()
    draft["severity"] = "ultra"
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["severity"] == "medium"
    assert any("severity" in w.lower() for w in warnings)


def test_sanitizer_coerces_window_minutes():
    draft = _valid_search_draft()
    draft["window_minutes"] = "bad"
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["window_minutes"] == 60


def test_sanitizer_interval_minimum_5():
    draft = _valid_search_draft()
    draft["interval_minutes"] = 1
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["interval_minutes"] == 5


def test_sanitizer_removes_empty_leg():
    draft = _valid_search_draft()
    draft["legs"].append("not a dict")
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert len(sanitized["legs"]) == 1
    assert any("invalid structure" in w.lower() for w in warnings)


def test_sanitizer_draft_not_persisted_or_activated():
    """Sanitiser returns a plain dict — no ORM save, no enabled=True override."""
    draft = _valid_search_draft()
    draft["enabled"] = False
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["enabled"] is False


# ── sanitize_search_draft: Diversity Constraint (ADR-0009) ─────────────────────

def _diversity_mapping():
    return {
        "rule.groups": "keyword",
        "GeoLocation.country_name": "keyword",
        "data.dstuser": "keyword",
        "rule.description": "text",
    }


def _diversity_draft(distinct_field="GeoLocation.country_name", min_distinct=2,
                     correlation_key="user.name"):
    return {
        "name": "Impossible travel",
        "description": "",
        "correlation_key": correlation_key,
        "severity": "high",
        "window_minutes": 60,
        "interval_minutes": 15,
        "max_findings_per_run": 50,
        "enabled": True,
        "legs": [{
            "count": 1,
            "display_order": 0,
            "distinct_field": distinct_field,
            "min_distinct": min_distinct,
            "conditions": [
                {"field_name": "rule.groups", "operator": "equals", "value": "authentication_success"},
            ],
        }],
    }


def test_sanitizer_preserves_valid_diversity():
    sanitized, warnings = sanitize_search_draft(_diversity_draft(), _diversity_mapping())
    leg = sanitized["legs"][0]
    assert leg["distinct_field"] == "GeoLocation.country_name"
    assert leg["min_distinct"] == 2
    assert warnings == []


def test_sanitizer_strips_diversity_when_key_is_none():
    sanitized, warnings = sanitize_search_draft(
        _diversity_draft(correlation_key="none"), _diversity_mapping()
    )
    assert "distinct_field" not in sanitized["legs"][0]
    assert any("removed" in w.lower() and "diversity" in w.lower() for w in warnings)


def test_sanitizer_strips_diversity_on_non_aggregatable_field():
    sanitized, warnings = sanitize_search_draft(
        _diversity_draft(distinct_field="rule.description"), _diversity_mapping()
    )
    assert "distinct_field" not in sanitized["legs"][0]
    assert any("removed" in w.lower() for w in warnings)


def test_sanitizer_strips_diversity_when_min_distinct_below_two():
    sanitized, warnings = sanitize_search_draft(
        _diversity_draft(min_distinct=1), _diversity_mapping()
    )
    assert "distinct_field" not in sanitized["legs"][0]
    assert any("removed" in w.lower() for w in warnings)


def test_sanitizer_strips_diversity_on_correlation_key_field():
    # user.name → data.dstuser; diversifying on the key field is a dead rule.
    sanitized, warnings = sanitize_search_draft(
        _diversity_draft(distinct_field="data.dstuser"), _diversity_mapping()
    )
    assert "distinct_field" not in sanitized["legs"][0]
    assert any("removed" in w.lower() for w in warnings)


def test_sanitizer_keeps_plain_leg_when_diversity_stripped():
    """Stripping the diversity must leave the leg intact as a plain count leg."""
    sanitized, _ = sanitize_search_draft(
        _diversity_draft(correlation_key="none"), _diversity_mapping()
    )
    leg = sanitized["legs"][0]
    assert leg["count"] == 1
    assert len(leg["conditions"]) == 1


@patch(_OS_CLIENT)
def test_grounding_core_fields_include_country(mock_cls):
    client = MagicMock()
    client.get_field_mapping.return_value = {}
    client.get_rule_catalog.return_value = {}
    mock_cls.return_value = client
    g = build_search_grounding()
    names = [f["value"] for f in g["core_fields"]]
    assert "GeoLocation.country_name" in names


# ── SearchRuleDraftView endpoint ───────────────────────────────────────────────

_MESSAGES = [{"role": "user", "content": "detect SSH brute force from external IPs"}]

_STUB_SEARCH_DRAFT = {
    "name": "SSH brute force",
    "description": "Repeated SSH failures",
    "correlation_key": "source.ip",
    "severity": "high",
    "window_minutes": 30,
    "interval_minutes": 15,
    "max_findings_per_run": 50,
    "enabled": True,
    "legs": [
        {
            "count": 5,
            "display_order": 0,
            "conditions": [
                {"field_name": "rule.id", "operator": "equals", "value": "5710"}
            ],
        }
    ],
}


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="pass", is_staff=False)


def _mock_provider(draft=None, selected_ids=None):
    provider = MagicMock()
    provider.select_relevant_rule_ids.return_value = selected_ids or ["5710"]
    provider.draft_search_rule.return_value = RuleDraftResult(
        updated_draft=draft or _STUB_SEARCH_DRAFT,
        assistant_reply="Detects SSH brute force.",
        warnings=[],
    )
    return provider


# Stub grounding so view tests don't make real OpenSearch calls.
_STUB_GROUNDING = {
    "rule_catalog": _STUB_CATALOG,
    "mapping": {"rule.id": "keyword", "rule.level": "long"},
    "core_fields": [{"value": "rule.id", "type": "keyword"}],
    "severities": ["critical", "high", "medium", "low", "info"],
    "correlation_keys": [{"value": "none", "label": "None"}],
    "expanded_fields": {},
}

_GROUNDING_PATCH = "correlations.llm.search_grounding.build_search_grounding"
_EXPAND_PATCH = "correlations.llm.search_grounding.expand_rule_fields"


@pytest.mark.django_db
def test_search_draft_requires_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.post(
        "/api/correlations/search-draft/",
        data=json.dumps({"messages": _MESSAGES}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_search_draft_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/correlations/search-draft/",
        data=json.dumps({"messages": _MESSAGES}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_search_draft_response_shape(client, staff_user):
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=_mock_provider()), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "updated_draft" in data
    assert "assistant_reply" in data
    assert "warnings" in data
    assert data["updated_draft"]["name"] == "SSH brute force"
    assert data["assistant_reply"] == "Detects SSH brute force."


@pytest.mark.django_db
def test_search_draft_two_pass_flow(client, staff_user):
    """Both pass 1 (select_relevant_rule_ids) and pass 2 (draft_search_rule) are called."""
    provider = _mock_provider()
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=provider), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    provider.select_relevant_rule_ids.assert_called_once()
    provider.draft_search_rule.assert_called_once()


@pytest.mark.django_db
def test_search_draft_injects_system_org(client, staff_user):
    """No scope → organization is None in the response."""
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=_mock_provider()), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.json()["updated_draft"]["organization"] is None


@pytest.mark.django_db
def test_search_draft_requires_messages(client, staff_user):
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=_mock_provider()), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": []}),
            content_type="application/json",
        )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_search_draft_unknown_scope_returns_400(client, staff_user):
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=_mock_provider()):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES, "scope": "nonexistent-org"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_search_draft_provider_unavailable_returns_503(client, staff_user):
    from correlations.llm.base import DraftConfigError
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", side_effect=DraftConfigError("no key")):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 503


@pytest.mark.django_db
def test_search_draft_provider_error_returns_502(client, staff_user):
    from correlations.llm.base import DraftError
    provider = MagicMock()
    provider.select_relevant_rule_ids.return_value = []
    provider.draft_search_rule.side_effect = DraftError("LLM failed")
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=provider), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 502


@pytest.mark.django_db
def test_search_draft_pass1_error_does_not_abort(client, staff_user):
    """If pass 1 (rule selection) fails, fall through to pass 2 with empty rule list."""
    from correlations.llm.base import DraftError
    provider = _mock_provider()
    provider.select_relevant_rule_ids.side_effect = DraftError("pass 1 failed")
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=provider), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    # Should still attempt pass 2 and return 200
    assert resp.status_code == 200
    provider.draft_search_rule.assert_called_once()


@pytest.mark.django_db
def test_search_draft_sanitizer_warnings_included(client, staff_user):
    """Sanitiser warnings appear in the response."""
    bad_draft = {**_STUB_SEARCH_DRAFT, "severity": "ultramax"}
    provider = _mock_provider(draft=bad_draft)
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=provider), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        resp = client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert len(resp.json()["warnings"]) > 0


@pytest.mark.django_db
def test_search_draft_nothing_persisted(client, staff_user, db):
    """Calling the endpoint never creates a SearchRule in the database."""
    from correlations.models import SearchRule
    initial_count = SearchRule.objects.count()
    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=_mock_provider()), \
         patch(_GROUNDING_PATCH, return_value=dict(_STUB_GROUNDING)), \
         patch(_EXPAND_PATCH, return_value={}):
        client.post(
            "/api/correlations/search-draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )
    assert SearchRule.objects.count() == initial_count


# ── sanitize_search_draft: time-of-day window (#440) ────────────────────────────


def test_sanitizer_default_draft_has_cleared_time_window():
    sanitized, _ = sanitize_search_draft(_valid_search_draft(), _stub_mapping())
    assert sanitized["time_window_start"] is None
    assert sanitized["time_window_end"] is None
    assert sanitized["time_window_days"] == []
    assert sanitized["time_window_mode"] == "inside"


def test_sanitizer_preserves_valid_time_window():
    draft = _valid_search_draft()
    draft.update({
        "time_window_start": "08:00",
        "time_window_end": "18:00",
        "time_window_days": [1, 2, 3, 4, 5],
        "time_window_mode": "outside",
    })
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_start"] == "08:00:00"
    assert sanitized["time_window_end"] == "18:00:00"
    assert sanitized["time_window_days"] == [1, 2, 3, 4, 5]
    assert sanitized["time_window_mode"] == "outside"


def test_sanitizer_keeps_cross_midnight_window():
    draft = _valid_search_draft()
    draft.update({"time_window_start": "22:00", "time_window_end": "06:00", "time_window_days": [6, 7]})
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_start"] == "22:00:00"
    assert sanitized["time_window_end"] == "06:00:00"
    assert sanitized["time_window_days"] == [6, 7]


def test_sanitizer_drops_window_missing_end_with_warning():
    draft = _valid_search_draft()
    draft.update({"time_window_start": "08:00", "time_window_days": [1]})
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_start"] is None
    assert any("Time-of-day window dropped" in w for w in warnings)


def test_sanitizer_drops_window_missing_days_with_warning():
    draft = _valid_search_draft()
    draft.update({"time_window_start": "08:00", "time_window_end": "18:00", "time_window_days": []})
    sanitized, warnings = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_days"] == []
    assert any("Time-of-day window dropped" in w for w in warnings)


def test_sanitizer_filters_invalid_day_values():
    draft = _valid_search_draft()
    draft.update({"time_window_start": "08:00", "time_window_end": "18:00", "time_window_days": [1, 9, 3, 3]})
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_days"] == [1, 3]


def test_sanitizer_unknown_mode_defaults_inside():
    draft = _valid_search_draft()
    draft.update({"time_window_start": "08:00", "time_window_end": "18:00", "time_window_days": [1], "time_window_mode": "bogus"})
    sanitized, _ = sanitize_search_draft(draft, _stub_mapping())
    assert sanitized["time_window_mode"] == "inside"


def test_search_draft_prompt_documents_time_window():
    from correlations.llm.search_prompt import build_search_draft_prompt
    prompt = build_search_draft_prompt(dict(_STUB_GROUNDING))
    assert "time_window_start" in prompt
    assert "time_window_mode" in prompt
    assert "outside" in prompt
