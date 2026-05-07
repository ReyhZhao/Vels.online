from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_WAZUH_AGENTS = [
    {
        "id": "001",
        "name": "server-01",
        "ip": "10.0.0.1",
        "status": "active",
        "os": {"name": "Ubuntu", "version": "22.04", "platform": "linux"},
        "lastKeepAlive": "2024-01-01T12:00:00Z",
    },
    {
        "id": "002",
        "name": "server-02",
        "ip": "10.0.0.2",
        "status": "disconnected",
        "os": {"name": "Windows", "version": "11", "platform": "windows"},
        "lastKeepAlive": "2024-01-01T10:00:00Z",
    },
]

_VULN_SUMMARY = {"critical": 2, "high": 5, "medium": 10, "low": 3}


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


# ---------------------------------------------------------------- GET /api/security/agents/


@pytest.mark.django_db
def test_agents_requires_authentication(client, acme):
    response = client.get("/api/security/agents/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_agents_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/agents/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_agents_admin_can_query_any_org(mock_wazuh_cls, admin_client, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    response = admin_client.get("/api/security/agents/?org=acme")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_agents_serialised_correctly(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    client.force_login(acme_member)
    response = client.get("/api/security/agents/?org=acme")
    assert response.status_code == 200
    first = response.json()[0]
    assert first["id"] == "001"
    assert first["name"] == "server-01"
    assert first["status"] == "active"
    assert first["os"] == "Ubuntu 22.04"
    assert first["last_seen"] == "2024-01-01T12:00:00Z"


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_agents_served_from_cache_on_second_request(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    client.force_login(acme_member)

    client.get("/api/security/agents/?org=acme")
    client.get("/api/security/agents/?org=acme")

    mock_wazuh_cls.return_value.get_agents.assert_called_once()


@pytest.mark.django_db
def test_agents_missing_org_param_returns_400(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/agents/")
    assert response.status_code == 400


# ---------------------------------------------------------------- GET /api/security/dashboard/


@pytest.mark.django_db
def test_dashboard_requires_authentication(client, acme):
    response = client.get("/api/security/dashboard/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_dashboard_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/dashboard/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
@patch("security.views.WazuhClient")
def test_dashboard_returns_fleet_stats(mock_wazuh_cls, mock_os_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    mock_os_cls.return_value.get_vulnerabilities_summary.return_value = _VULN_SUMMARY
    mock_os_cls.return_value.get_events_count.return_value = 42
    client.force_login(acme_member)

    response = client.get("/api/security/dashboard/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["agent_count"] == 2
    assert data["active_count"] == 1
    assert data["vulnerabilities"] == _VULN_SUMMARY
    assert data["events_24h"] == 42


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
@patch("security.views.WazuhClient")
def test_dashboard_served_from_cache_on_second_request(mock_wazuh_cls, mock_os_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    mock_os_cls.return_value.get_vulnerabilities_summary.return_value = _VULN_SUMMARY
    mock_os_cls.return_value.get_events_count.return_value = 0
    client.force_login(acme_member)

    client.get("/api/security/dashboard/?org=acme")
    client.get("/api/security/dashboard/?org=acme")

    mock_wazuh_cls.return_value.get_agents.assert_called_once()


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
@patch("security.views.WazuhClient")
def test_dashboard_admin_can_query_any_org(mock_wazuh_cls, mock_os_cls, admin_client, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = []
    mock_os_cls.return_value.get_vulnerabilities_summary.return_value = _VULN_SUMMARY
    mock_os_cls.return_value.get_events_count.return_value = 0
    response = admin_client.get("/api/security/dashboard/?org=acme")
    assert response.status_code == 200


# ---------------------------------------------------------------- POST /api/security/dashboard/refresh/


@pytest.mark.django_db
def test_refresh_requires_authentication(client, acme):
    response = client.post("/api/security/dashboard/refresh/", {"org": "acme"}, content_type="application/json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.post("/api/security/dashboard/refresh/", {"org": "acme"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
@patch("security.views.WazuhClient")
def test_refresh_busts_dashboard_cache(mock_wazuh_cls, mock_os_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    mock_os_cls.return_value.get_vulnerabilities_summary.return_value = _VULN_SUMMARY
    mock_os_cls.return_value.get_events_count.return_value = 0
    client.force_login(acme_member)

    client.get("/api/security/dashboard/?org=acme")
    assert mock_wazuh_cls.return_value.get_agents.call_count == 1

    client.post("/api/security/dashboard/refresh/", {"org": "acme"}, content_type="application/json")

    client.get("/api/security/dashboard/?org=acme")
    assert mock_wazuh_cls.return_value.get_agents.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_refresh_busts_agents_cache(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agents.return_value = _WAZUH_AGENTS
    client.force_login(acme_member)

    client.get("/api/security/agents/?org=acme")
    assert mock_wazuh_cls.return_value.get_agents.call_count == 1

    client.post("/api/security/dashboard/refresh/", {"org": "acme"}, content_type="application/json")

    client.get("/api/security/agents/?org=acme")
    assert mock_wazuh_cls.return_value.get_agents.call_count == 2


@pytest.mark.django_db
def test_refresh_missing_org_returns_400(client, acme_member):
    client.force_login(acme_member)
    response = client.post("/api/security/dashboard/refresh/", {}, content_type="application/json")
    assert response.status_code == 400
