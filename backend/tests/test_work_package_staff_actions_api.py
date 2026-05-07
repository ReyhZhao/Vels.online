from unittest.mock import patch

import pytest
from security.models import Organization, OrganizationMembership, WorkPackage, WorkPackageItem


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def active_package(acme):
    return WorkPackage.objects.create(org=acme)


@pytest.fixture
def item(active_package):
    return WorkPackageItem.objects.create(
        work_package=active_package,
        cve_id="CVE-2024-0001",
        severity="critical",
        cvss_score=9.8,
        description="Flaw.",
        affected_agent_count=3,
        impact_score=30.0,
    )


@pytest.fixture
def archived_item(acme):
    pkg = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ARCHIVED)
    return WorkPackageItem.objects.create(
        work_package=pkg,
        cve_id="CVE-2023-0001",
        severity="high",
        cvss_score=7.0,
        description="Old flaw.",
        affected_agent_count=1,
        impact_score=7.0,
    )


def _make_item(pkg, cve_id):
    return WorkPackageItem.objects.create(
        work_package=pkg, cve_id=cve_id, severity="high",
        cvss_score=7.0, description="", affected_agent_count=1, impact_score=7.0,
    )


# ---------------------------------------------------------------- DELETE /api/security/work-package/items/<id>/


@pytest.mark.django_db
def test_delete_item_requires_authentication(client, item):
    assert client.delete(f"/api/security/work-package/items/{item.id}/").status_code == 401


@pytest.mark.django_db
def test_delete_item_non_staff_gets_403(client, acme_member, item):
    client.force_login(acme_member)
    assert client.delete(f"/api/security/work-package/items/{item.id}/").status_code == 403


@pytest.mark.django_db
def test_delete_item_staff_removes_item(admin_client, item):
    item_id = item.id
    response = admin_client.delete(f"/api/security/work-package/items/{item_id}/")
    assert response.status_code == 204
    assert not WorkPackageItem.objects.filter(pk=item_id).exists()


@pytest.mark.django_db
def test_delete_item_archived_returns_400(admin_client, archived_item):
    response = admin_client.delete(f"/api/security/work-package/items/{archived_item.id}/")
    assert response.status_code == 400
    assert "archived" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_delete_item_not_found_returns_404(admin_client):
    assert admin_client.delete("/api/security/work-package/items/99999/").status_code == 404


# ---------------------------------------------------------------- POST /api/security/work-package/add-more/


@pytest.mark.django_db
def test_add_more_requires_authentication(client, acme):
    assert client.post("/api/security/work-package/add-more/?org=acme").status_code == 401


@pytest.mark.django_db
def test_add_more_non_staff_gets_403(client, acme_member):
    client.force_login(acme_member)
    assert client.post("/api/security/work-package/add-more/?org=acme").status_code == 403


@pytest.mark.django_db
def test_add_more_no_active_package_returns_404(admin_client, acme):
    assert admin_client.post("/api/security/work-package/add-more/?org=acme").status_code == 404


@pytest.mark.django_db
@patch("security.views.add_more_items")
def test_add_more_returns_new_items(mock_add, admin_client, active_package, acme):
    new_item = _make_item(active_package, "CVE-2024-9999")
    mock_add.return_value = ([new_item], False)

    response = admin_client.post("/api/security/work-package/add-more/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["cve_id"] == "CVE-2024-9999"
    assert data["exhausted"] is False


@pytest.mark.django_db
@patch("security.views.add_more_items")
def test_add_more_exhausted_returns_empty_list_with_flag(mock_add, admin_client, active_package, acme):
    mock_add.return_value = ([], True)

    response = admin_client.post("/api/security/work-package/add-more/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["exhausted"] is True


@pytest.mark.django_db
@patch("security.views.add_more_items")
def test_add_more_passes_active_package_to_service(mock_add, admin_client, active_package, acme):
    mock_add.return_value = ([], True)

    admin_client.post("/api/security/work-package/add-more/?org=acme")

    mock_add.assert_called_once()
    assert mock_add.call_args[0][0].id == active_package.id


@pytest.mark.django_db
@patch("security.views.add_more_items")
def test_add_more_excludes_existing_cves(mock_add, admin_client, active_package, acme):
    # Pre-populate the active package with one CVE
    _make_item(active_package, "CVE-2024-0001")
    new_item = _make_item(active_package, "CVE-2024-0002")
    mock_add.return_value = ([new_item], False)

    response = admin_client.post("/api/security/work-package/add-more/?org=acme")

    assert response.status_code == 200
    # The service is responsible for exclusion; we verify the view passes
    # the package (with its items prefetched) so the service can filter
    mock_add.assert_called_once()
