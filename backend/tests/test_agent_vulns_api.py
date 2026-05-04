from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_OPENSEARCH_VULNS = [
    {
        "vulnerability": {"id": "CVE-2024-0001", "severity": "High", "status": "Fixed"},
        "package": {"name": "openssl", "version": "1.1.1"},
        "agent": {"id": "001", "name": "server-01"},
    },
    {
        "vulnerability": {"id": "CVE-2024-0002", "severity": "Critical", "status": "Unfixed"},
        "package": {"name": "curl", "version": "7.68.0"},
        "agent": {"id": "001", "name": "server-01"},
    },
    {
        "vulnerability": {"id": "CVE-2024-0003", "severity": "Medium", "status": "Fixed"},
        "package": {"name": "libc6", "version": "2.31"},
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


# ---------------------------------------------------------------- GET /api/security/agents/<id>/vulnerabilities/


@pytest.mark.django_db
def test_vulns_requires_authentication(client, acme):
    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_vulns_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_serialised_correctly(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _OPENSEARCH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    vulns = data["vulnerabilities"]
    assert len(vulns) == 3

    # First entry should be Critical (sorted to top)
    assert vulns[0]["cve"] == "CVE-2024-0002"
    assert vulns[0]["severity"] == "critical"
    assert vulns[0]["package"] == "curl"
    assert vulns[0]["version"] == "7.68.0"
    assert vulns[0]["fix_available"] is False


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_sorted_critical_first(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _OPENSEARCH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    severities = [v["severity"] for v in response.json()["vulnerabilities"]]

    assert severities == ["critical", "high", "medium"]


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_fix_available_flag(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _OPENSEARCH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    vulns = {v["cve"]: v for v in response.json()["vulnerabilities"]}

    assert vulns["CVE-2024-0001"]["fix_available"] is True   # status: Fixed
    assert vulns["CVE-2024-0002"]["fix_available"] is False  # status: Unfixed
    assert vulns["CVE-2024-0003"]["fix_available"] is True   # status: Fixed


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_cached_for_one_hour(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _OPENSEARCH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once()


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_offset_and_limit_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": [],
        "total": 200,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once_with(
        "001", offset=50, limit=50, severity=None, fix_available=None, search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_paginated_vulns_not_cached(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": [],
        "total": 200,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")

    assert mock_os_cls.return_value.get_agent_vulnerabilities.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
@patch("security.views.OpenSearchClient")
def test_refresh_busts_vulns_cache(mock_os_cls, mock_wazuh_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _OPENSEARCH_VULNS,
        "total": 3,
    }
    mock_wazuh_cls.return_value.get_agents.return_value = [{"id": "001"}]
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert mock_os_cls.return_value.get_agent_vulnerabilities.call_count == 1

    # Refresh busts agents cache and vulns cache
    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme", "agent_id": "001"},
        content_type="application/json",
    )

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert mock_os_cls.return_value.get_agent_vulnerabilities.call_count == 2


@pytest.mark.django_db
def test_vulns_cross_org_agent_id_gets_403(client, acme_member, acme):
    client.force_login(acme_member)
    # Agent "999" does not belong to acme — cache has only "001"
    response = client.get("/api/security/agents/999/vulnerabilities/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_staff_bypasses_agent_ownership_check(mock_os_cls, client, acme, django_user_model):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": [], "total": 0}
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)
    # Agent "999" is not in acme's agent list, but staff is exempt
    response = client.get("/api/security/agents/999/vulnerabilities/?org=acme")
    assert response.status_code == 200


# ---------------------------------------------------------------- Filter params


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_severity_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&severity=critical,high")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once_with(
        "001", offset=0, limit=50, severity=["critical", "high"], fix_available=None, search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_fix_available_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&fix_available=true")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once_with(
        "001", offset=0, limit=50, severity=None, fix_available=True, search=""
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_search_param_forwarded(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": [], "total": 0}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&search=openssl")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once_with(
        "001", offset=0, limit=50, severity=None, fix_available=None, search="openssl"
    )


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_filter_combos_have_distinct_cache_keys(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": _OPENSEARCH_VULNS, "total": 3}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme&severity=critical")

    assert mock_os_cls.return_value.get_agent_vulnerabilities.call_count == 2


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vulns_same_filter_combo_served_from_cache(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_agent_vulnerabilities.return_value = {"vulnerabilities": _OPENSEARCH_VULNS, "total": 3}
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&severity=critical&fix_available=true")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme&severity=critical&fix_available=true")

    mock_os_cls.return_value.get_agent_vulnerabilities.assert_called_once()


@pytest.mark.django_db
def test_vulns_ownership_check_applies_with_filters(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/agents/999/vulnerabilities/?org=acme&severity=critical&fix_available=true")
    assert response.status_code == 403
