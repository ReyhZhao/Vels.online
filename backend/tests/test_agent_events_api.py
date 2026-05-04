from unittest.mock import patch, call

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_OPENSEARCH_EVENTS = [
    {
        "_id": "evt-abc-001",
        "@timestamp": "2024-01-15T10:00:00Z",
        "rule": {"description": "SSH brute force", "level": 10, "id": "5710"},
        "agent": {"id": "001", "name": "server-01"},
    },
    {
        "_id": "evt-xyz-002",
        "@timestamp": "2024-01-15T09:00:00Z",
        "rule": {"description": "Sudo usage", "level": 5, "id": "5402"},
        "agent": {"id": "001", "name": "server-01"},
    },
]


_ACME_AGENT_CACHE = [
    {"id": "001", "name": "server-01", "ip": "10.0.0.1", "status": "active", "os": "Ubuntu 20.04", "last_seen": "2024-01-15T10:00:00Z"},
]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    cache.set("security_agents_acme", _ACME_AGENT_CACHE, 3600)
    yield
    cache.clear()


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


# ---------------------------------------------------------------- GET /api/security/agents/<id>/events/


@pytest.mark.django_db
def test_events_requires_authentication(client, acme):
    response = client.get("/api/security/agents/001/events/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_events_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/agents/001/events/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_returns_serialised_events(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {
        "events": _OPENSEARCH_EVENTS,
        "total": 2,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["events"]) == 2
    first = data["events"][0]
    assert first["id"] == "evt-abc-001"
    assert first["timestamp"] == "2024-01-15T10:00:00Z"
    assert first["rule_description"] == "SSH brute force"
    assert first["severity"] == "high"   # level 10 → high
    assert first["agent_name"] == "server-01"


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_severity_mapping(mock_os_cls, client, acme_member, acme):
    events = [
        {"@timestamp": "T", "rule": {"level": 2, "description": "d", "id": "1"}, "agent": {"name": "a"}},
        {"@timestamp": "T", "rule": {"level": 5, "description": "d", "id": "2"}, "agent": {"name": "a"}},
        {"@timestamp": "T", "rule": {"level": 9, "description": "d", "id": "3"}, "agent": {"name": "a"}},
        {"@timestamp": "T", "rule": {"level": 13, "description": "d", "id": "4"}, "agent": {"name": "a"}},
    ]
    mock_os_cls.return_value.get_agent_events.return_value = {"events": events, "total": 4}
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/?org=acme")
    severities = [e["severity"] for e in response.json()["events"]]

    assert severities == ["low", "medium", "high", "critical"]


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_cached_for_five_minutes(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": _OPENSEARCH_EVENTS, "total": 2}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme")
    client.get("/api/security/agents/001/events/?org=acme")

    mock_os_cls.return_value.get_agent_events.assert_called_once()


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_offset_and_limit_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 250}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=50")

    mock_os_cls.return_value.get_agent_events.assert_called_once_with(
        "001", hours=24, offset=100, limit=50, severity=None, search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_paginated_events_not_cached(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 250}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=100")
    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=100")

    assert mock_os_cls.return_value.get_agent_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
@patch("security.views.OpenSearchClient")
def test_refresh_busts_events_cache_when_agent_id_provided(mock_os_cls, mock_wazuh_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": _OPENSEARCH_EVENTS, "total": 2}
    mock_wazuh_cls.return_value.get_agents.return_value = [{"id": "001"}]
    client.force_login(acme_member)

    # Populate cache
    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_os_cls.return_value.get_agent_events.call_count == 1

    # Refresh busts the agents cache and the events cache
    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme", "agent_id": "001"},
        content_type="application/json",
    )

    # Cache is busted — OpenSearch is called again
    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_os_cls.return_value.get_agent_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
@patch("security.views.OpenSearchClient")
def test_refresh_without_agent_id_leaves_events_cache(mock_os_cls, mock_wazuh_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": _OPENSEARCH_EVENTS, "total": 2}
    mock_wazuh_cls.return_value.get_agents.return_value = [{"id": "001"}]
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_os_cls.return_value.get_agent_events.call_count == 1

    # Refresh without agent_id busts agents cache but leaves events cache intact
    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme"},
        content_type="application/json",
    )

    client.get("/api/security/agents/001/events/?org=acme")
    # Events cache untouched — still served from cache
    assert mock_os_cls.return_value.get_agent_events.call_count == 1


@pytest.mark.django_db
def test_events_cross_org_agent_id_gets_403(client, acme_member, acme):
    client.force_login(acme_member)
    # Agent "999" does not belong to acme — cache has only "001"
    response = client.get("/api/security/agents/999/events/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_staff_bypasses_agent_ownership_check(mock_os_cls, client, acme, django_user_model):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 0}
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)
    # Agent "999" is not in acme's agent list, but staff is exempt
    response = client.get("/api/security/agents/999/events/?org=acme")
    assert response.status_code == 200


# ---------------------------------------------------------------- Filter params


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_severity_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&severity=critical,high")

    mock_os_cls.return_value.get_agent_events.assert_called_once_with(
        "001", hours=24, offset=0, limit=100, severity=["critical", "high"], search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_hours_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&hours=6")

    mock_os_cls.return_value.get_agent_events.assert_called_once_with(
        "001", hours=6, offset=0, limit=100, severity=None, search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_search_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&search=brute+force")

    mock_os_cls.return_value.get_agent_events.assert_called_once_with(
        "001", hours=24, offset=0, limit=100, severity=None, search="brute force"
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_filter_combos_have_distinct_cache_keys(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": _OPENSEARCH_EVENTS, "total": 2}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme")
    client.get("/api/security/agents/001/events/?org=acme&severity=critical")

    assert mock_os_cls.return_value.get_agent_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_events_same_filter_combo_served_from_cache(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_events.return_value = {"events": _OPENSEARCH_EVENTS, "total": 2}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&severity=critical&hours=6")
    client.get("/api/security/agents/001/events/?org=acme&severity=critical&hours=6")

    mock_os_cls.return_value.get_agent_events.assert_called_once()


@pytest.mark.django_db
def test_events_ownership_check_applies_with_filters(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/agents/999/events/?org=acme&severity=critical&hours=6")
    assert response.status_code == 403
