from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_OPENSEARCH_EVENTS = [
    {
        "_id": "evt-fleet-001",
        "@timestamp": "2024-01-15T10:00:00Z",
        "rule": {"description": "SSH brute force", "level": 10, "id": "5710"},
        "agent": {"id": "001", "name": "server-01"},
    },
    {
        "_id": "evt-fleet-002",
        "@timestamp": "2024-01-15T09:00:00Z",
        "rule": {"description": "Rootkit detected", "level": 13, "id": "9999"},
        "agent": {"id": "002", "name": "server-02"},
    },
]

_FLEET_STATS = {
    "critical": 1,
    "high": 1,
    "medium": 0,
    "low": 0,
    "total": 2,
    "events_24h": 5,
}

_ACME_AGENTS_CACHE = [
    {"id": "001", "name": "server-01", "ip": "10.0.0.1", "status": "active", "os": "Ubuntu 20.04", "last_seen": "2024-01-15T10:00:00Z"},
    {"id": "002", "name": "server-02", "ip": "10.0.0.2", "status": "active", "os": "Debian 11", "last_seen": "2024-01-15T09:00:00Z"},
]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    cache.set("security_agents_acme", _ACME_AGENTS_CACHE, 3600)
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


# ---------------------------------------------------------------- GET /api/security/events/


@pytest.mark.django_db
def test_fleet_events_requires_authentication(client, acme):
    response = client.get("/api/security/events/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_fleet_events_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/events/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_returns_events_and_stats(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": _OPENSEARCH_EVENTS,
        "total": 2,
        "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/events/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["events"]) == 2

    first = data["events"][0]
    assert first["id"] == "evt-fleet-001"
    assert first["timestamp"] == "2024-01-15T10:00:00Z"
    assert first["rule_description"] == "SSH brute force"
    assert first["severity"] == "high"
    assert first["agent_id"] == "001"
    assert first["agent_name"] == "server-01"

    stats = data["stats"]
    assert stats["critical"] == 1
    assert stats["high"] == 1
    assert stats["events_24h"] == 5


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_severity_mapping(mock_os_cls, client, acme_member, acme):
    events = [
        {"_id": "a", "@timestamp": "T", "rule": {"level": 2,  "description": "d", "id": "1"}, "agent": {"id": "001", "name": "a"}},
        {"_id": "b", "@timestamp": "T", "rule": {"level": 5,  "description": "d", "id": "2"}, "agent": {"id": "001", "name": "a"}},
        {"_id": "c", "@timestamp": "T", "rule": {"level": 9,  "description": "d", "id": "3"}, "agent": {"id": "001", "name": "a"}},
        {"_id": "d", "@timestamp": "T", "rule": {"level": 13, "description": "d", "id": "4"}, "agent": {"id": "001", "name": "a"}},
    ]
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": events, "total": 4, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/events/?org=acme")
    severities = [e["severity"] for e in response.json()["events"]]

    assert severities == ["low", "medium", "high", "critical"]


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_cached_for_one_minute(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": _OPENSEARCH_EVENTS, "total": 2, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme")
    client.get("/api/security/events/?org=acme")

    mock_os_cls.return_value.get_fleet_events.assert_called_once()


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_paginated_not_cached(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 500, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme&offset=100")
    client.get("/api/security/events/?org=acme&offset=100")

    assert mock_os_cls.return_value.get_fleet_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_minutes_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 0, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme&minutes=60")

    mock_os_cls.return_value.get_fleet_events.assert_called_once_with(
        ["001", "002"],
        minutes=60,
        offset=0,
        limit=100,
        severity=None,
        search="",
        agent_id_filter=None,
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_invalid_minutes_returns_400(mock_os_cls, client, acme_member, acme):
    client.force_login(acme_member)

    response = client.get("/api/security/events/?org=acme&minutes=999")

    assert response.status_code == 400


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_severity_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 0, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme&severity=critical,high")

    mock_os_cls.return_value.get_fleet_events.assert_called_once_with(
        ["001", "002"],
        minutes=1440,
        offset=0,
        limit=100,
        severity=["critical", "high"],
        search="",
        agent_id_filter=None,
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_search_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 0, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme&search=brute+force")

    mock_os_cls.return_value.get_fleet_events.assert_called_once_with(
        ["001", "002"],
        minutes=1440,
        offset=0,
        limit=100,
        severity=None,
        search="brute force",
        agent_id_filter=None,
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_agent_filter_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 0, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme&agent=001")

    mock_os_cls.return_value.get_fleet_events.assert_called_once_with(
        ["001", "002"],
        minutes=1440,
        offset=0,
        limit=100,
        severity=None,
        search="",
        agent_id_filter="001",
    )


@pytest.mark.django_db
def test_fleet_events_unknown_agent_filter_gets_403(client, acme_member, acme):
    client.force_login(acme_member)

    response = client.get("/api/security/events/?org=acme&agent=999")

    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_staff_can_use_any_agent_filter(mock_os_cls, client, acme, django_user_model):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": [], "total": 0, "stats": _FLEET_STATS,
    }
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)

    response = client.get("/api/security/events/?org=acme&agent=999")

    assert response.status_code == 200


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_fleet_events_filter_combos_have_distinct_cache_keys(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_fleet_events.return_value = {
        "events": _OPENSEARCH_EVENTS, "total": 2, "stats": _FLEET_STATS,
    }
    client.force_login(acme_member)

    client.get("/api/security/events/?org=acme")
    client.get("/api/security/events/?org=acme&severity=critical")

    assert mock_os_cls.return_value.get_fleet_events.call_count == 2


@pytest.mark.django_db
def test_fleet_events_missing_agent_cache_returns_503(client, acme_member, acme):
    cache.clear()  # remove the agent cache set in autouse fixture
    client.force_login(acme_member)

    response = client.get("/api/security/events/?org=acme")

    assert response.status_code == 503
