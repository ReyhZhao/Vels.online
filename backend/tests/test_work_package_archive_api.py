import pytest
from security.models import Organization, OrganizationMembership, WorkPackage, WorkPackageItem


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def _make_archived(acme, cve_id="CVE-2024-0001", n_items=2):
    pkg = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ARCHIVED)
    for i in range(n_items):
        WorkPackageItem.objects.create(
            work_package=pkg,
            cve_id=f"{cve_id}-{i}",
            severity="high",
            cvss_score=7.0,
            description="Flaw.",
            affected_agent_count=1,
            impact_score=7.0,
        )
    return pkg


# ---------------------------------------------------------------- GET /api/security/work-packages/archive/


@pytest.mark.django_db
def test_archive_list_requires_authentication(client, acme):
    assert client.get("/api/security/work-packages/archive/?org=acme").status_code == 401


@pytest.mark.django_db
def test_archive_list_non_member_gets_403(client, alice, acme):
    client.force_login(alice)
    assert client.get("/api/security/work-packages/archive/?org=acme").status_code == 403


@pytest.mark.django_db
def test_archive_list_wrong_org_gets_403(client, acme_member, contoso):
    client.force_login(acme_member)
    assert client.get("/api/security/work-packages/archive/?org=contoso").status_code == 403


@pytest.mark.django_db
def test_archive_list_empty_when_no_archives(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/work-packages/archive/?org=acme")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_archive_list_returns_archived_packages(client, acme_member, acme):
    pkg1 = _make_archived(acme)
    pkg2 = _make_archived(acme, cve_id="CVE-2023-0001")
    client.force_login(acme_member)
    response = client.get("/api/security/work-packages/archive/?org=acme")
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert pkg1.id in ids
    assert pkg2.id in ids


@pytest.mark.django_db
def test_archive_list_ordered_newest_first(client, acme_member, acme):
    older = _make_archived(acme)
    newer = _make_archived(acme, cve_id="CVE-2024-9999")
    # Force a created_at ordering difference
    WorkPackage.objects.filter(pk=older.pk).update(created_at="2024-01-01T00:00:00Z")
    WorkPackage.objects.filter(pk=newer.pk).update(created_at="2024-06-01T00:00:00Z")
    client.force_login(acme_member)
    response = client.get("/api/security/work-packages/archive/?org=acme")
    ids = [p["id"] for p in response.json()]
    assert ids.index(newer.id) < ids.index(older.id)


@pytest.mark.django_db
def test_archive_list_includes_item_count(client, acme_member, acme):
    _make_archived(acme, n_items=3)
    client.force_login(acme_member)
    response = client.get("/api/security/work-packages/archive/?org=acme")
    assert response.json()[0]["item_count"] == 3


@pytest.mark.django_db
def test_archive_list_does_not_include_active_package(client, acme_member, acme):
    active = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ACTIVE)
    _make_archived(acme)
    client.force_login(acme_member)
    response = client.get("/api/security/work-packages/archive/?org=acme")
    ids = [p["id"] for p in response.json()]
    assert active.id not in ids


@pytest.mark.django_db
def test_archive_list_staff_can_access_any_org(admin_client, acme):
    _make_archived(acme)
    response = admin_client.get("/api/security/work-packages/archive/?org=acme")
    assert response.status_code == 200
    assert len(response.json()) == 1


# ---------------------------------------------------------------- GET /api/security/work-packages/<id>/


@pytest.mark.django_db
def test_package_detail_requires_authentication(client, acme):
    pkg = _make_archived(acme)
    assert client.get(f"/api/security/work-packages/{pkg.id}/?org=acme").status_code == 401


@pytest.mark.django_db
def test_package_detail_non_member_gets_403(client, alice, acme):
    pkg = _make_archived(acme)
    client.force_login(alice)
    assert client.get(f"/api/security/work-packages/{pkg.id}/?org=acme").status_code == 403


@pytest.mark.django_db
def test_package_detail_non_member_of_requested_org_gets_403(client, acme_member, contoso):
    # acme_member requests with ?org=contoso — they're not a contoso member
    other_pkg = _make_archived(contoso)
    client.force_login(acme_member)
    assert client.get(f"/api/security/work-packages/{other_pkg.id}/?org=contoso").status_code == 403


@pytest.mark.django_db
def test_package_detail_package_outside_org_scope_returns_404(client, acme_member, contoso):
    # acme_member scopes to acme but requests a package that belongs to contoso
    other_pkg = _make_archived(contoso)
    client.force_login(acme_member)
    assert client.get(f"/api/security/work-packages/{other_pkg.id}/?org=acme").status_code == 404


@pytest.mark.django_db
def test_package_detail_returns_archived_package_with_items(client, acme_member, acme):
    pkg = _make_archived(acme, n_items=2)
    client.force_login(acme_member)
    response = client.get(f"/api/security/work-packages/{pkg.id}/?org=acme")
    assert response.status_code == 200
    data = response.json()
    assert data["package"]["id"] == pkg.id
    assert data["package"]["status"] == "archived"
    assert len(data["package"]["items"]) == 2


@pytest.mark.django_db
def test_package_detail_returns_active_package(client, acme_member, acme):
    active = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ACTIVE)
    client.force_login(acme_member)
    response = client.get(f"/api/security/work-packages/{active.id}/?org=acme")
    assert response.status_code == 200
    assert response.json()["package"]["status"] == "active"


@pytest.mark.django_db
def test_package_detail_not_found_returns_404(client, acme_member, acme):
    client.force_login(acme_member)
    assert client.get("/api/security/work-packages/99999/?org=acme").status_code == 404


@pytest.mark.django_db
def test_package_detail_package_from_other_org_returns_404(client, acme_member, contoso):
    contoso_pkg = _make_archived(contoso)
    # unauthenticated client gets 401 before org resolution
    response = client.get(f"/api/security/work-packages/{contoso_pkg.id}/?org=acme")
    assert response.status_code == 401
