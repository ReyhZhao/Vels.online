from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_WAZUH_VULNS = [
    {
        "cve": "CVE-2024-0001",
        "severity": "High",
        "name": "openssl",
        "version": "1.1.1",
        "condition": "Package fixed in: 1.1.2",
    },
    {
        "cve": "CVE-2024-0002",
        "severity": "Critical",
        "name": "curl",
        "version": "7.68.0",
        "condition": "Package unfixed",
    },
    {
        "cve": "CVE-2024-0003",
        "severity": "Medium",
        "name": "libc6",
        "version": "2.31",
        "condition": "Package fixed in: 2.32",
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
@patch("security.views.WazuhClient")
def test_vulns_serialised_correctly(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _WAZUH_VULNS,
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
@patch("security.views.WazuhClient")
def test_vulns_sorted_critical_first(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _WAZUH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    severities = [v["severity"] for v in response.json()["vulnerabilities"]]

    assert severities == ["critical", "high", "medium"]


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_vulns_fix_available_flag(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _WAZUH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    vulns = {v["cve"]: v for v in response.json()["vulnerabilities"]}

    assert vulns["CVE-2024-0001"]["fix_available"] is True   # "Package fixed in: 1.1.2"
    assert vulns["CVE-2024-0002"]["fix_available"] is False  # "Package unfixed"
    assert vulns["CVE-2024-0003"]["fix_available"] is True   # "Package fixed in: 2.32"


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_vulns_cached_for_one_hour(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _WAZUH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme")

    mock_wazuh_cls.return_value.get_agent_vulnerabilities.assert_called_once()


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_vulns_offset_and_limit_forwarded_to_wazuh(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": [],
        "total": 200,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")

    mock_wazuh_cls.return_value.get_agent_vulnerabilities.assert_called_once_with(
        "001", offset=50, limit=50
    )


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_paginated_vulns_not_cached(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": [],
        "total": 200,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")
    client.get("/api/security/agents/001/vulnerabilities/?org=acme&offset=50&limit=50")

    assert mock_wazuh_cls.return_value.get_agent_vulnerabilities.call_count == 2


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_refresh_busts_vulns_cache(mock_wazuh_cls, client, acme_member, acme):
    mock_wazuh_cls.return_value.get_agent_vulnerabilities.return_value = {
        "vulnerabilities": _WAZUH_VULNS,
        "total": 3,
    }
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert mock_wazuh_cls.return_value.get_agent_vulnerabilities.call_count == 1

    client.post(
        "/api/security/dashboard/refresh/",
        {"org": "acme", "agent_id": "001"},
        content_type="application/json",
    )

    client.get("/api/security/agents/001/vulnerabilities/?org=acme")
    assert mock_wazuh_cls.return_value.get_agent_vulnerabilities.call_count == 2
