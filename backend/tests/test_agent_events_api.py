from unittest.mock import patch, call

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_WAZUH_EVENTS = [
    {
        "timestamp": "2024-01-15T10:00:00Z",
        "rule": {"description": "SSH brute force", "level": 10, "id": "5710"},
        "agent": {"id": "001", "name": "server-01"},
    },
    {
        "timestamp": "2024-01-15T09:00:00Z",
        "rule": {"description": "Sudo usage", "level": 5, "id": "5402"},
        "agent": {"id": "001", "name": "server-01"},
    },
]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
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
@patch("security.views.WazuhClient")
def test_events_returns_serialised_events(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {
        "events": _WAZUH_EVENTS,
        "total": 2,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["events"]) == 2
    first = data["events"][0]
    assert first["timestamp"] == "2024-01-15T10:00:00Z"
    assert first["rule_description"] == "SSH brute force"
    assert first["severity"] == "high"   # level 10 → high
    assert first["agent_name"] == "server-01"


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_events_severity_mapping(mock_wazuh_cls, client, acme_member, acme):
    events = [
        {"timestamp": "T", "rule": {"level": 2, "description": "d", "id": "1"}, "agent": {"name": "a"}},
        {"timestamp": "T", "rule": {"level": 5, "description": "d", "id": "2"}, "agent": {"name": "a"}},
        {"timestamp": "T", "rule": {"level": 9, "description": "d", "id": "3"}, "agent": {"name": "a"}},
        {"timestamp": "T", "rule": {"level": 13, "description": "d", "id": "4"}, "agent": {"name": "a"}},
    ]
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": events, "total": 4}
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/?org=acme")
    severities = [e["severity"] for e in response.json()["events"]]

    assert severities == ["low", "medium", "high", "critical"]


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_events_cached_for_five_minutes(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": _WAZUH_EVENTS, "total": 2}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme")
    client.get("/api/security/agents/001/events/?org=acme")

    mock_wazuh_cls.return_value.get_agent_events.assert_called_once()


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_events_offset_and_limit_forwarded_to_wazuh(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": [], "total": 250}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=50")

    mock_wazuh_cls.return_value.get_agent_events.assert_called_once_with(
        "001", hours=24, offset=100, limit=50
    )


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_paginated_events_not_cached(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": [], "total": 250}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=100")
    client.get("/api/security/agents/001/events/?org=acme&offset=100&limit=100")

    assert mock_wazuh_cls.return_value.get_agent_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_refresh_busts_events_cache_when_agent_id_provided(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": _WAZUH_EVENTS, "total": 2}
    client.force_login(acme_member)

    # Populate cache
    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_wazuh_cls.return_value.get_agent_events.call_count == 1

    # Refresh with agent_id
    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme", "agent_id": "001"},
        content_type="application/json",
    )

    # Cache is busted — Wazuh is called again
    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_wazuh_cls.return_value.get_agent_events.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_refresh_without_agent_id_leaves_events_cache(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_events.return_value = {"events": _WAZUH_EVENTS, "total": 2}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/events/?org=acme")
    assert mock_wazuh_cls.return_value.get_agent_events.call_count == 1

    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme"},
        content_type="application/json",
    )

    client.get("/api/security/agents/001/events/?org=acme")
    # Events cache untouched — still served from cache
    assert mock_wazuh_cls.return_value.get_agent_events.call_count == 1
