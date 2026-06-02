"""Tests for AssetListView (POST) and AssetDetailView (PATCH) is_permanent handling."""
import pytest
from incidents.models import Asset
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def host_asset(acme):
    return Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="srv-01",
        agent_name="srv-01",
        ip_address="10.0.0.1",
        is_permanent=False,
    )


# ── POST /api/assets/ ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_asset_with_is_permanent_true(client, staff, acme):
    client.force_login(staff)
    resp = client.post(
        "/api/assets/",
        {"kind": "host", "organization": acme.slug, "name": "new-host", "agent_name": "new-host", "is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["is_permanent"] is True
    assert Asset.objects.get(agent_name="new-host").is_permanent is True


@pytest.mark.django_db
def test_create_asset_without_is_permanent_defaults_false(client, staff, acme):
    client.force_login(staff)
    resp = client.post(
        "/api/assets/",
        {"kind": "host", "organization": acme.slug, "name": "new-host2", "agent_name": "new-host2"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["is_permanent"] is False


# ── PATCH /api/assets/<id>/ ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_is_permanent_true(client, staff, host_asset):
    client.force_login(staff)
    resp = client.patch(
        f"/api/assets/{host_asset.pk}/",
        {"is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_permanent"] is True
    host_asset.refresh_from_db()
    assert host_asset.is_permanent is True


@pytest.mark.django_db
def test_patch_is_permanent_false(client, staff, host_asset):
    host_asset.is_permanent = True
    host_asset.save(update_fields=["is_permanent"])
    client.force_login(staff)
    resp = client.patch(
        f"/api/assets/{host_asset.pk}/",
        {"is_permanent": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_permanent"] is False
    host_asset.refresh_from_db()
    assert host_asset.is_permanent is False


@pytest.mark.django_db
def test_patch_name_still_works(client, staff, host_asset):
    client.force_login(staff)
    resp = client.patch(
        f"/api/assets/{host_asset.pk}/",
        {"name": "renamed"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"


@pytest.mark.django_db
def test_patch_omitting_is_permanent_leaves_it_unchanged(client, staff, host_asset):
    host_asset.is_permanent = True
    host_asset.save(update_fields=["is_permanent"])
    client.force_login(staff)
    resp = client.patch(
        f"/api/assets/{host_asset.pk}/",
        {"name": "still-renamed"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    host_asset.refresh_from_db()
    assert host_asset.is_permanent is True


# ── POST /api/assets/bulk/ ───────────────────────────────────────────────────


@pytest.fixture
def host_asset2(acme):
    return Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="srv-02",
        agent_name="srv-02",
        is_permanent=False,
    )


@pytest.mark.django_db
def test_bulk_update_is_permanent(client, staff, host_asset, host_asset2):
    client.force_login(staff)
    resp = client.post(
        "/api/assets/bulk/",
        {"ids": [host_asset.pk, host_asset2.pk], "is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    host_asset.refresh_from_db()
    host_asset2.refresh_from_db()
    assert host_asset.is_permanent is True
    assert host_asset2.is_permanent is True


@pytest.mark.django_db
def test_bulk_update_requires_auth(client, host_asset):
    resp = client.post(
        "/api/assets/bulk/",
        {"ids": [host_asset.pk], "is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_bulk_update_empty_ids_rejected(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/assets/bulk/",
        {"ids": [], "is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_update_no_fields_rejected(client, staff, host_asset):
    client.force_login(staff)
    resp = client.post(
        "/api/assets/bulk/",
        {"ids": [host_asset.pk]},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_update_non_member_cannot_update_asset(client, django_user_model, host_asset):
    outsider = django_user_model.objects.create_user(username="outsider", password="pass")
    client.force_login(outsider)
    resp = client.post(
        "/api/assets/bulk/",
        {"ids": [host_asset.pk], "is_permanent": True},
        content_type="application/json",
    )
    assert resp.status_code == 404
    host_asset.refresh_from_db()
    assert host_asset.is_permanent is False
