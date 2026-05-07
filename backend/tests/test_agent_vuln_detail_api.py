from unittest.mock import patch

import pytest
from django.core.cache import cache

from security.models import Organization, OrganizationMembership

_FULL_VULN = {
    "_id": "vuln-abc-001",
    "vulnerability": {
        "id": "CVE-2024-0001",
        "severity": "High",
        "status": "Fixed",
        "cvss": {"cvss3": {"base_score": 7.8}},
        "description": "A buffer overflow in openssl allows remote attackers...",
        "published": "2024-01-10T00:00:00Z",
        "references": [
            "https://nvd.nist.gov/vuln/detail/CVE-2024-0001",
            "https://openssl.org/advisory/CVE-2024-0001",
        ],
    },
    "package": {
        "name": "openssl",
        "version": "1.1.1",
        "fixed_version": "1.1.1w",
    },
    "agent": {"id": "001", "name": "server-01"},
}

_MINIMAL_VULN = {
    "_id": "vuln-xyz-002",
    "vulnerability": {
        "id": "CVE-2024-0002",
        "severity": "Medium",
        "status": "Unfixed",
    },
    "package": {
        "name": "curl",
        "version": "7.68.0",
    },
    "agent": {"id": "001", "name": "server-01"},
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


# ---------------------------------------------------------------- GET /api/security/agents/<id>/vulnerabilities/<vuln_id>/


@pytest.mark.django_db
def test_vuln_detail_requires_authentication(client, acme):
    response = client.get("/api/security/agents/001/vulnerabilities/vuln-abc-001/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_vuln_detail_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/agents/001/vulnerabilities/vuln-abc-001/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vuln_detail_returns_full_payload(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_vulnerability_by_id.return_value = _FULL_VULN
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/vuln-abc-001/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "vuln-abc-001"
    assert data["cve"] == "CVE-2024-0001"
    assert data["severity"] == "high"
    assert data["cvss_score"] == 7.8
    assert data["package"] == "openssl"
    assert data["installed_version"] == "1.1.1"
    assert data["fixed_version"] == "1.1.1w"
    assert "buffer overflow" in data["description"]
    assert data["published"] == "2024-01-10T00:00:00Z"
    assert len(data["references"]) == 2
    assert "nvd.nist.gov" in data["references"][0]


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vuln_detail_not_found_returns_404(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_vulnerability_by_id.return_value = None
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/nonexistent/?org=acme")
    assert response.status_code == 404


@pytest.mark.django_db
def test_vuln_detail_cross_org_agent_gets_403(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/agents/999/vulnerabilities/vuln-abc-001/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vuln_detail_staff_bypasses_ownership_check(mock_os_cls, client, acme, django_user_model):
    mock_os_cls.return_value.get_vulnerability_by_id.return_value = _FULL_VULN
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(staff)
    response = client.get("/api/security/agents/999/vulnerabilities/vuln-abc-001/?org=acme")
    assert response.status_code == 200


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vuln_detail_references_absent_when_not_in_source(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_vulnerability_by_id.return_value = _MINIMAL_VULN
    client.force_login(acme_member)

    response = client.get("/api/security/agents/001/vulnerabilities/vuln-xyz-002/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert "references" not in data


@pytest.mark.django_db
@patch("security.views.OpenSearchClient")
def test_vuln_detail_calls_opensearch_with_agent_and_vuln_id(mock_os_cls, client, acme_member, acme):
    mock_os_cls.return_value.get_vulnerability_by_id.return_value = _FULL_VULN
    client.force_login(acme_member)

    client.get("/api/security/agents/001/vulnerabilities/vuln-abc-001/?org=acme")

    mock_os_cls.return_value.get_vulnerability_by_id.assert_called_once_with("001", "vuln-abc-001")
