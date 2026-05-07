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
        description="A critical flaw.",
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


def patch(client, item_id, data):
    return client.patch(
        f"/api/security/work-package/items/{item_id}/",
        data,
        content_type="application/json",
    )


# ---------------------------------------------------------------- auth / access


@pytest.mark.django_db
def test_patch_requires_authentication(client, item):
    response = patch(client, item.id, {"status": "in_progress"})
    assert response.status_code == 401


@pytest.mark.django_db
def test_patch_non_member_gets_403(client, alice, item):
    client.force_login(alice)
    response = patch(client, item.id, {"status": "in_progress"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_wrong_org_member_gets_403(client, alice, contoso, item):
    OrganizationMembership.objects.create(user=alice, organization=contoso)
    client.force_login(alice)
    response = patch(client, item.id, {"status": "in_progress"})
    assert response.status_code == 403


# ---------------------------------------------------------------- archived guard


@pytest.mark.django_db
def test_patch_archived_item_returns_400(client, acme_member, archived_item):
    client.force_login(acme_member)
    response = patch(client, archived_item.id, {"status": "resolved"})
    assert response.status_code == 400
    assert "archived" in response.json()["detail"].lower()


# ---------------------------------------------------------------- valid updates


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["open", "in_progress", "resolved", "accepted_risk"])
def test_patch_all_valid_statuses(client, acme_member, item, status):
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": status})
    assert response.status_code == 200
    assert response.json()["status"] == status


@pytest.mark.django_db
def test_patch_accepted_risk_saves_note(client, acme_member, item):
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": "accepted_risk", "note": "Low priority for us."})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted_risk"
    assert data["note"] == "Low priority for us."


@pytest.mark.django_db
def test_patch_non_accepted_risk_clears_note(client, acme_member, item):
    item.status = "accepted_risk"
    item.note = "Old note."
    item.save()
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": "resolved"})
    assert response.status_code == 200
    assert response.json()["note"] == ""


@pytest.mark.django_db
def test_patch_note_ignored_for_non_accepted_risk(client, acme_member, item):
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": "in_progress", "note": "Should be discarded"})
    assert response.status_code == 200
    assert response.json()["note"] == ""


@pytest.mark.django_db
def test_patch_returns_full_item_fields(client, acme_member, item):
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": "in_progress"})
    assert response.status_code == 200
    data = response.json()
    assert data["cve_id"] == "CVE-2024-0001"
    assert data["severity"] == "critical"
    assert data["cvss_score"] == 9.8
    assert "affected_agent_count" in data
    assert "impact_score" in data


@pytest.mark.django_db
def test_patch_invalid_status_returns_400(client, acme_member, item):
    client.force_login(acme_member)
    response = patch(client, item.id, {"status": "pending"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_patch_nonexistent_item_returns_404(client, acme_member):
    client.force_login(acme_member)
    response = patch(client, 99999, {"status": "open"})
    assert response.status_code == 404


@pytest.mark.django_db
def test_patch_staff_can_update_any_org_item(admin_client, item):
    response = patch(admin_client, item.id, {"status": "resolved"})
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


@pytest.mark.django_db
def test_patch_persists_to_database(client, acme_member, item):
    client.force_login(acme_member)
    patch(client, item.id, {"status": "resolved"})
    item.refresh_from_db()
    assert item.status == "resolved"
