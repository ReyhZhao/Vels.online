import pytest
from security.models import Organization, OrganizationMembership, WorkPackage, WorkPackageItem


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


@pytest.fixture
def active_package(acme):
    pkg = WorkPackage.objects.create(org=acme)
    WorkPackageItem.objects.create(
        work_package=pkg,
        cve_id="CVE-2024-0001",
        severity="critical",
        cvss_score=9.8,
        description="A critical buffer overflow.",
        references=["https://nvd.nist.gov/vuln/detail/CVE-2024-0001"],
        affected_agent_count=3,
        impact_score=30.0,
        affected_agents=[
            {
                "agent_id": "001",
                "hostname": "web-01",
                "package_name": "libssl",
                "current_version": "1.1.1f",
                "fixed_version": None,
                "patch_job_id": None,
            }
        ],
    )
    WorkPackageItem.objects.create(
        work_package=pkg,
        cve_id="CVE-2024-0002",
        severity="high",
        cvss_score=7.5,
        description="A high-severity injection flaw.",
        references=[],
        affected_agent_count=2,
        impact_score=14.0,
        affected_agents=[],
    )
    return pkg


# ---------------------------------------------------------------- GET /api/security/work-package/


@pytest.mark.django_db
def test_work_package_requires_authentication(client, acme):
    response = client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_work_package_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_work_package_missing_org_gets_400(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_work_package_wrong_org_gets_403(client, acme_member, contoso):
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/?org=contoso")
    assert response.status_code == 403


@pytest.mark.django_db
def test_work_package_empty_state_when_no_package(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 200
    assert response.json()["package"] is None


@pytest.mark.django_db
def test_work_package_returns_active_package(client, acme_member, active_package):
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 200
    data = response.json()
    assert data["package"] is not None
    assert data["package"]["id"] == active_package.id


@pytest.mark.django_db
def test_work_package_returns_all_item_fields(client, acme_member, active_package):
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/?org=acme")
    items = response.json()["package"]["items"]
    assert len(items) == 2
    item = next(i for i in items if i["cve_id"] == "CVE-2024-0001")
    assert item["severity"] == "critical"
    assert item["cvss_score"] == 9.8
    assert item["description"] == "A critical buffer overflow."
    assert item["references"] == ["https://nvd.nist.gov/vuln/detail/CVE-2024-0001"]
    assert item["affected_agent_count"] == 3
    assert item["impact_score"] == 30.0
    assert item["status"] == "open"
    assert item["note"] == ""
    assert len(item["affected_agents"]) == 1
    assert item["affected_agents"][0]["hostname"] == "web-01"


@pytest.mark.django_db
def test_work_package_does_not_return_archived_package(client, acme_member, acme):
    archived = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ARCHIVED)
    WorkPackageItem.objects.create(
        work_package=archived,
        cve_id="CVE-2023-9999",
        severity="low",
        cvss_score=2.0,
        description="Old.",
        affected_agent_count=1,
        impact_score=1.0,
    )
    client.force_login(acme_member)
    response = client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 200
    assert response.json()["package"] is None


@pytest.mark.django_db
def test_work_package_staff_can_access_any_org(admin_client, active_package):
    response = admin_client.get("/api/security/work-package/?org=acme")
    assert response.status_code == 200
    assert response.json()["package"]["id"] == active_package.id
