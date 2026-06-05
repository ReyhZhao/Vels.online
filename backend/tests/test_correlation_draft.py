import itertools
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from alerts.models import Alert, AlertEntity
from alerts.services.identifiers import next_alert_display_id
from correlations.llm.base import RuleDraftResult
from correlations.llm.gemini import _build_system_prompt
from correlations.llm.grounding import build_grounding
from correlations.llm.sanitizer import sanitize_draft
from security.models import Organization


# ── Grounding builder ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_grounding_has_all_field_kinds():
    g = build_grounding()
    assert set(g["field_catalog"].keys()) == {"alert_field", "entity", "source_ref"}


@pytest.mark.django_db
def test_grounding_alert_field_vocabulary():
    g = build_grounding()
    fields = g["field_catalog"]["alert_field"]
    assert "severity" in fields
    assert "source_kind" in fields
    assert "title" in fields


@pytest.mark.django_db
def test_grounding_entity_vocabulary():
    g = build_grounding()
    fields = g["field_catalog"]["entity"]
    assert "host.name" in fields
    assert "user.name" in fields


@pytest.mark.django_db
def test_grounding_source_ref_vocabulary():
    g = build_grounding()
    fields = g["field_catalog"]["source_ref"]
    assert "rule_id" in fields


@pytest.mark.django_db
def test_grounding_operators_alert_field():
    g = build_grounding()
    ops = g["allowed_operators"]["alert_field"]
    assert "equals" in ops
    assert "gte" in ops
    assert "cidr" not in ops


@pytest.mark.django_db
def test_grounding_operators_entity_includes_cidr():
    g = build_grounding()
    assert "cidr" in g["allowed_operators"]["entity"]


@pytest.mark.django_db
def test_grounding_operators_source_ref_excludes_gte():
    g = build_grounding()
    ops = g["allowed_operators"]["source_ref"]
    assert "gte" not in ops
    assert "equals" in ops


@pytest.mark.django_db
def test_grounding_correlation_keys():
    g = build_grounding()
    assert "none" in g["correlation_keys"]
    assert "host.name" in g["correlation_keys"]


@pytest.mark.django_db
def test_grounding_severities():
    g = build_grounding()
    assert set(g["severities"]) == {"critical", "high", "medium", "low", "info"}


# ── Grounding builder: corpus (DB) ─────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org", slug="test-org", wazuh_group="test")


def _make_alert(org, source_kind="wazuh_event", severity="high", title="Test Alert",
                source_ref=None):
    return Alert.objects.create(
        display_id=next_alert_display_id(),
        organization=org,
        source_kind=source_kind,
        severity=severity,
        title=title,
        source_ref=source_ref or {},
    )


def _make_entity(alert, org, entity_type="host.name", value="server-01"):
    return AlertEntity.objects.create(
        alert=alert,
        organization=org,
        entity_type=entity_type,
        value=value,
    )


@pytest.mark.django_db
def test_grounding_source_kinds_with_counts(org):
    now = timezone.now()
    for _ in range(3):
        _make_alert(org, source_kind="wazuh_event")
    for _ in range(2):
        _make_alert(org, source_kind="vulnerability")

    g = build_grounding(scope="test-org", now=now)
    assert g["source_kinds"]["wazuh_event"] == 3
    assert g["source_kinds"]["vulnerability"] == 2


@pytest.mark.django_db
def test_grounding_severity_distribution(org):
    now = timezone.now()
    _make_alert(org, severity="high")
    _make_alert(org, severity="high")
    _make_alert(org, severity="critical")

    g = build_grounding(scope="test-org", now=now)
    assert g["severity_distribution"]["high"] == 2
    assert g["severity_distribution"]["critical"] == 1


@pytest.mark.django_db
def test_grounding_entity_types_populated(org):
    now = timezone.now()
    a = _make_alert(org)
    _make_entity(a, org, entity_type="host.name", value="web-01")
    _make_entity(a, org, entity_type="user.name", value="alice")

    g = build_grounding(scope="test-org", now=now)
    assert "host.name" in g["entity_types"]
    assert "user.name" in g["entity_types"]


@pytest.mark.django_db
def test_grounding_source_ref_keys(org):
    now = timezone.now()
    _make_alert(org, source_ref={"rule_id": "100001", "level": "9"})

    g = build_grounding(scope="test-org", now=now)
    assert "rule_id" in g["source_ref_keys"]
    assert "level" in g["source_ref_keys"]


@pytest.mark.django_db
def test_grounding_top_alert_field_values(org):
    now = timezone.now()
    _make_alert(org, source_kind="wazuh_event", title="Brute force detected")
    _make_alert(org, source_kind="wazuh_event", title="Lateral movement")

    g = build_grounding(scope="test-org", now=now)
    top = g["top_values"]["alert_field"]
    assert "wazuh_event" in top.get("source_kind", [])
    titles = top.get("title", [])
    assert "Brute force detected" in titles or "Lateral movement" in titles


@pytest.mark.django_db
def test_grounding_sample_cap_enforced(org):
    now = timezone.now()
    cap = 3
    for i in range(cap + 2):
        _make_alert(org, title=f"Alert {i}")

    with override_settings(GROUNDING_SAMPLE_CAP=cap):
        g = build_grounding(scope="test-org", now=now)

    assert len(g["sample_alerts"]) == cap


@pytest.mark.django_db
def test_grounding_value_cap_enforced(org):
    now = timezone.now()
    cap = 3
    for i in range(cap + 2):
        _make_alert(org, title=f"Unique Title {i:04d}")

    with override_settings(GROUNDING_VALUE_CAP=cap):
        g = build_grounding(scope="test-org", now=now)

    top_titles = g["top_values"]["alert_field"].get("title", [])
    assert len(top_titles) <= cap


@pytest.mark.django_db
def test_grounding_source_ref_value_cap_enforced(org):
    now = timezone.now()
    cap = 2
    for i in range(cap + 2):
        _make_alert(org, source_ref={"rule_id": f"RULE-{i:04d}"})

    with override_settings(GROUNDING_VALUE_CAP=cap):
        g = build_grounding(scope="test-org", now=now)

    sr_top = g["top_values"]["source_ref"]
    if "rule_id" in sr_top:
        assert len(sr_top["rule_id"]) <= cap


@pytest.mark.django_db
def test_grounding_window_excludes_old_alerts(org):
    now = timezone.now()
    a = _make_alert(org, source_kind="vulnerability")
    Alert.objects.filter(pk=a.pk).update(created_at=now - timedelta(days=35))

    with override_settings(GROUNDING_WINDOW_DAYS=30):
        g = build_grounding(scope="test-org", now=now)

    assert "vulnerability" not in g["source_kinds"]
    assert g["sample_alerts"] == []


@pytest.mark.django_db
def test_grounding_scope_filters_by_org(db):
    now = timezone.now()
    org_a = Organization.objects.create(name="Org A", slug="org-a", wazuh_group="a")
    org_b = Organization.objects.create(name="Org B", slug="org-b", wazuh_group="b")
    _make_alert(org_a, source_kind="wazuh_event")
    _make_alert(org_b, source_kind="vulnerability")

    g = build_grounding(scope="org-a", now=now)
    assert "wazuh_event" in g["source_kinds"]
    assert "vulnerability" not in g["source_kinds"]


@pytest.mark.django_db
def test_grounding_all_scope_includes_all_orgs(db):
    now = timezone.now()
    org_a = Organization.objects.create(name="Org A", slug="org-a", wazuh_group="a")
    org_b = Organization.objects.create(name="Org B", slug="org-b", wazuh_group="b")
    _make_alert(org_a, source_kind="wazuh_event")
    _make_alert(org_b, source_kind="vulnerability")

    g = build_grounding(scope="all", now=now)
    assert "wazuh_event" in g["source_kinds"]
    assert "vulnerability" in g["source_kinds"]


def test_build_system_prompt_includes_corpus_data():
    """_build_system_prompt renders corpus fields (source_kinds, samples, top values) into the prompt."""
    from correlations.models import (
        ALERT_FIELD_CATALOG, CORRELATION_KEY_CHOICES, ENTITY_CATALOG,
        FIELD_KIND_ALERT, FIELD_KIND_ENTITY, FIELD_KIND_SOURCE_REF, SOURCE_REF_CATALOG,
    )
    grounding = {
        "field_catalog": {
            FIELD_KIND_ALERT: sorted(ALERT_FIELD_CATALOG),
            FIELD_KIND_ENTITY: sorted(ENTITY_CATALOG),
            FIELD_KIND_SOURCE_REF: sorted(SOURCE_REF_CATALOG),
        },
        "allowed_operators": {
            FIELD_KIND_ALERT: ["equals", "in"],
            FIELD_KIND_ENTITY: ["equals", "cidr"],
            FIELD_KIND_SOURCE_REF: ["equals"],
        },
        "severities": ["critical", "high", "medium", "low", "info"],
        "correlation_keys": [k for k, _ in CORRELATION_KEY_CHOICES],
        "source_kinds": {"wazuh_event": 42},
        "severity_distribution": {"high": 10, "critical": 5},
        "entity_types": ["host.name", "user.name"],
        "source_ref_keys": ["rule_id"],
        "top_values": {
            "alert_field": {"title": ["Brute force", "Lateral movement"]},
            "entity": {"host.name": ["web-01"]},
            "source_ref": {"rule_id": ["100001"]},
        },
        "sample_alerts": [
            {
                "source_kind": "wazuh_event",
                "severity": "high",
                "title": "Real Alert",
                "source_ref": {"rule_id": "100001"},
                "entities": {"host.name": ["web-01"]},
            }
        ],
    }

    prompt = _build_system_prompt(grounding)

    assert "wazuh_event" in prompt
    assert "rule_id" in prompt
    assert "host.name" in prompt
    assert "Real Alert" in prompt
    assert "Brute force" in prompt


# ── Draft sanitizer ────────────────────────────────────────────────────────────

def _valid_draft(**overrides):
    base = {
        "name": "Test rule",
        "description": "A test",
        "correlation_key": "none",
        "window_minutes": 30,
        "severity": "medium",
        "enabled": True,
        "legs": [
            {
                "count": 2,
                "display_order": 0,
                "conditions": [
                    {
                        "field_kind": "alert_field",
                        "field_name": "source_kind",
                        "operator": "equals",
                        "value": "wazuh_event",
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def test_sanitizer_valid_passthrough():
    draft = _valid_draft()
    sanitized, warnings = sanitize_draft(draft)
    assert warnings == []
    assert sanitized["name"] == "Test rule"
    assert len(sanitized["legs"]) == 1
    assert sanitized["legs"][0]["conditions"][0]["field_name"] == "source_kind"


def test_sanitizer_strips_unknown_field():
    draft = _valid_draft()
    draft["legs"][0]["conditions"][0]["field_name"] = "not_a_real_field"
    sanitized, warnings = sanitize_draft(draft)
    assert len(warnings) == 1
    assert "not_a_real_field" in warnings[0]
    assert sanitized["legs"][0]["conditions"] == []


def test_sanitizer_strips_disallowed_operator():
    draft = _valid_draft()
    # cidr is not allowed for alert_field
    draft["legs"][0]["conditions"][0]["operator"] = "cidr"
    sanitized, warnings = sanitize_draft(draft)
    assert len(warnings) == 1
    assert "cidr" in warnings[0]
    assert sanitized["legs"][0]["conditions"] == []


def test_sanitizer_unknown_field_kind():
    draft = _valid_draft()
    draft["legs"][0]["conditions"][0]["field_kind"] = "mystery_kind"
    sanitized, warnings = sanitize_draft(draft)
    assert len(warnings) == 1
    assert "mystery_kind" in warnings[0]
    assert sanitized["legs"][0]["conditions"] == []


def test_sanitizer_bad_severity_defaults_to_medium():
    draft = _valid_draft(severity="extreme")
    sanitized, warnings = sanitize_draft(draft)
    assert sanitized["severity"] == "medium"
    assert any("extreme" in w for w in warnings)


def test_sanitizer_bad_corr_key_defaults_to_none():
    draft = _valid_draft(correlation_key="not.valid")
    sanitized, warnings = sanitize_draft(draft)
    assert sanitized["correlation_key"] == "none"
    assert any("not.valid" in w for w in warnings)


def test_sanitizer_multiple_legs_partial_strip():
    draft = _valid_draft()
    draft["legs"].append({
        "count": 1,
        "display_order": 1,
        "conditions": [
            {
                "field_kind": "entity",
                "field_name": "host.name",
                "operator": "equals",
                "value": "server-01",
            },
            {
                "field_kind": "entity",
                "field_name": "bad_field",
                "operator": "equals",
                "value": "x",
            },
        ],
    })
    sanitized, warnings = sanitize_draft(draft)
    assert len(sanitized["legs"]) == 2
    assert len(sanitized["legs"][1]["conditions"]) == 1
    assert len(warnings) == 1


# ── Draft endpoint ─────────────────────────────────────────────────────────────

@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="pass", is_staff=False)


_STUB_DRAFT = {
    "name": "Stubbed brute force rule",
    "description": "Detects repeated failed logins",
    "correlation_key": "user.name",
    "window_minutes": 10,
    "severity": "high",
    "enabled": True,
    "legs": [
        {
            "count": 5,
            "display_order": 0,
            "conditions": [
                {
                    "field_kind": "alert_field",
                    "field_name": "severity",
                    "operator": "equals",
                    "value": "high",
                }
            ],
        }
    ],
}

_MESSAGES = [{"role": "user", "content": "detect brute force login attempts"}]


@pytest.mark.django_db
def test_draft_requires_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.post(
        "/api/correlations/draft/",
        data=json.dumps({"messages": _MESSAGES}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_draft_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/correlations/draft/",
        data=json.dumps({"messages": _MESSAGES}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_draft_response_shape(client, staff_user):
    mock_result = RuleDraftResult(
        updated_draft=_STUB_DRAFT,
        assistant_reply="This rule detects brute force attempts.",
        warnings=[],
    )
    mock_provider = MagicMock()
    mock_provider.draft_rule.return_value = mock_result

    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=mock_provider):
        resp = client.post(
            "/api/correlations/draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "updated_draft" in data
    assert "assistant_reply" in data
    assert "warnings" in data
    assert data["updated_draft"]["name"] == "Stubbed brute force rule"
    assert data["assistant_reply"] == "This rule detects brute force attempts."


@pytest.mark.django_db
def test_draft_updated_draft_deserializes_into_builder(client, staff_user):
    """updated_draft must contain all fields the rule builder drawer reads."""
    mock_result = RuleDraftResult(updated_draft=_STUB_DRAFT, assistant_reply="ok", warnings=[])
    mock_provider = MagicMock()
    mock_provider.draft_rule.return_value = mock_result

    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=mock_provider):
        resp = client.post(
            "/api/correlations/draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )

    draft = resp.json()["updated_draft"]
    assert "name" in draft
    assert "correlation_key" in draft
    assert "window_minutes" in draft
    assert "severity" in draft
    assert "enabled" in draft
    assert "legs" in draft
    leg = draft["legs"][0]
    assert "count" in leg
    assert "display_order" in leg
    assert "conditions" in leg
    cond = leg["conditions"][0]
    assert "field_kind" in cond
    assert "field_name" in cond
    assert "operator" in cond
    assert "value" in cond


@pytest.mark.django_db
def test_draft_unconfigured_provider_returns_503(client, staff_user):
    from correlations.llm.base import DraftConfigError

    client.force_login(staff_user)
    with patch(
        "correlations.views.get_draft_provider",
        side_effect=DraftConfigError("GEMINI_API_KEY is not configured."),
    ):
        resp = client.post(
            "/api/correlations/draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )

    assert resp.status_code == 503
    data = resp.json()
    assert "unavailable" in data["detail"].lower()


@pytest.mark.django_db
def test_draft_missing_messages_returns_400(client, staff_user):
    client.force_login(staff_user)
    resp = client.post(
        "/api/correlations/draft/",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_draft_sanitizer_runs_on_provider_output(client, staff_user):
    """Sanitizer strips bad conditions from the provider's draft before returning."""
    bad_draft = {
        **_STUB_DRAFT,
        "legs": [
            {
                "count": 1,
                "display_order": 0,
                "conditions": [
                    {
                        "field_kind": "alert_field",
                        "field_name": "completely_unknown",
                        "operator": "equals",
                        "value": "x",
                    }
                ],
            }
        ],
    }
    mock_result = RuleDraftResult(updated_draft=bad_draft, assistant_reply="ok", warnings=[])
    mock_provider = MagicMock()
    mock_provider.draft_rule.return_value = mock_result

    client.force_login(staff_user)
    with patch("correlations.views.get_draft_provider", return_value=mock_provider):
        resp = client.post(
            "/api/correlations/draft/",
            data=json.dumps({"messages": _MESSAGES}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_draft"]["legs"][0]["conditions"] == []
    assert len(data["warnings"]) >= 1
