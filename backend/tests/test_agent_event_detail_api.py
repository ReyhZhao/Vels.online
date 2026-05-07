from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_FULL_EVENT = {
    "_id": "evt-abc-001",
    "@timestamp": "2024-01-15T10:00:00Z",
    "rule": {
        "description": "SSH brute force",
        "level": 10,
        "id": "5710",
        "groups": ["authentication_failures", "sshd"],
        "mitre": {
            "tactic": ["Credential Access"],
            "technique": ["Brute Force"],
            "id": ["T1110"],
        },
    },
    "agent": {"id": "001", "name": "server-01", "ip": "10.0.0.1"},
    "location": "/var/log/auth.log",
    "full_log": "Jan 15 10:00:00 server-01 sshd: Failed password for root from 192.168.1.100",
    "data": {"srcip": "192.168.1.100", "dstip": "10.0.0.1", "protocol": "tcp"},
}

_MINIMAL_EVENT = {
    "_id": "evt-xyz-002",
    "@timestamp": "2024-01-15T09:00:00Z",
    "rule": {"description": "Sudo usage", "level": 5, "id": "5402", "groups": ["sudo"]},
    "agent": {"id": "001", "name": "server-01", "ip": "10.0.0.1"},
    "location": "/var/log/auth.log",
    "full_log": "Jan 15 09:00:00 server-01 sudo: alice",
}

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


# ---------------------------------------------------------------- GET /api/security/agents/<id>/events/<event_id>/


@pytest.mark.django_db
def test_event_detail_requires_authentication(client, acme):
    response = client.get("/api/security/agents/001/events/evt-abc-001/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_event_detail_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/agents/001/events/evt-abc-001/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_event_detail_returns_full_payload(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_event_by_id.return_value = _FULL_EVENT
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/evt-abc-001/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "evt-abc-001"
    assert data["timestamp"] == "2024-01-15T10:00:00Z"
    assert data["severity"] == "high"
    assert data["rule_description"] == "SSH brute force"
    assert data["rule_id"] == "5710"
    assert data["level"] == 10
    assert data["rule_groups"] == ["authentication_failures", "sshd"]
    assert data["agent_name"] == "server-01"
    assert data["agent_ip"] == "10.0.0.1"
    assert data["log_source"] == "/var/log/auth.log"
    assert "Failed password" in data["raw_log"]
    assert data["mitre"]["tactic"] == ["Credential Access"]
    assert data["mitre"]["technique"] == ["Brute Force"]
    assert data["mitre"]["technique_id"] == ["T1110"]
    assert data["network"]["src_ip"] == "192.168.1.100"
    assert data["network"]["dst_ip"] == "10.0.0.1"
    assert data["network"]["protocol"] == "tcp"


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_event_detail_not_found_returns_404(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_event_by_id.return_value = None
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/nonexistent/?org=acme")
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_detail_cross_org_agent_gets_403(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/agents/999/events/evt-abc-001/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_event_detail_staff_bypasses_ownership_check(mock_os_cls, client, acme, django_user_model):
    mock_os_cls.return_value.get_event_by_id.return_value = _FULL_EVENT
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)
    response = client.get("/api/security/agents/999/events/evt-abc-001/?org=acme")
    assert response.status_code == 200


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_event_detail_mitre_absent_when_not_in_source(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_event_by_id.return_value = _MINIMAL_EVENT
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/evt-xyz-002/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert "mitre" not in data


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_event_detail_network_absent_when_not_in_source(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_event_by_id.return_value = _MINIMAL_EVENT
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/events/evt-xyz-002/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert "network" not in data
