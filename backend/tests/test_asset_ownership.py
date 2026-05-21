import pytest
from contacts.models import AssetOwner, Contact
from incidents.models import Asset
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


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


def make_contact(org, email="alice@example.com"):
    return Contact.objects.create(organisation=org, name="Alice", email=email)


def make_asset(org, name="host-1"):
    return Asset.objects.create(organization=org, kind=Asset.KIND_HOST, name=name, agent_name=name)


# ── GET /api/contacts/<id>/assets/ ────────────────────────────────────────────


@pytest.mark.django_db
def test_list_assets_requires_auth(client, acme):
    c = make_contact(acme)
    assert client.get(f"/api/contacts/{c.id}/assets/").status_code == 401


@pytest.mark.django_db
def test_list_owned_assets(client, acme_member, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    AssetOwner.objects.create(contact=c, asset=a)
    client.force_login(acme_member)
    data = client.get(f"/api/contacts/{c.id}/assets/").json()
    assert len(data) == 1
    assert data[0]["name"] == "host-1"


@pytest.mark.django_db
def test_list_contact_with_no_assets(client, acme_member, acme):
    c = make_contact(acme)
    client.force_login(acme_member)
    data = client.get(f"/api/contacts/{c.id}/assets/").json()
    assert data == []


# ── POST /api/contacts/<id>/assets/ ───────────────────────────────────────────


@pytest.mark.django_db
def test_assign_asset_requires_auth(client, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    assert client.post(f"/api/contacts/{c.id}/assets/", {"asset_id": a.id}, content_type="application/json").status_code == 401


@pytest.mark.django_db
def test_assign_asset_creates_ownership(client, acme_member, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    client.force_login(acme_member)
    resp = client.post(f"/api/contacts/{c.id}/assets/", {"asset_id": a.id}, content_type="application/json")
    assert resp.status_code == 201
    assert AssetOwner.objects.filter(contact=c, asset=a).exists()


@pytest.mark.django_db
def test_assign_asset_idempotent(client, acme_member, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    AssetOwner.objects.create(contact=c, asset=a)
    client.force_login(acme_member)
    resp = client.post(f"/api/contacts/{c.id}/assets/", {"asset_id": a.id}, content_type="application/json")
    assert resp.status_code == 201
    assert AssetOwner.objects.filter(contact=c, asset=a).count() == 1


@pytest.mark.django_db
def test_assign_asset_from_different_org_rejected(client, acme_member, acme, contoso):
    c = make_contact(acme)
    other_asset = make_asset(contoso, name="other-host")
    client.force_login(acme_member)
    resp = client.post(f"/api/contacts/{c.id}/assets/", {"asset_id": other_asset.id}, content_type="application/json")
    assert resp.status_code == 400


# ── DELETE /api/contacts/<id>/assets/<asset_id>/ ──────────────────────────────


@pytest.mark.django_db
def test_remove_asset_requires_auth(client, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    assert client.delete(f"/api/contacts/{c.id}/assets/{a.id}/").status_code == 401


@pytest.mark.django_db
def test_remove_asset_removes_ownership(client, acme_member, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    AssetOwner.objects.create(contact=c, asset=a)
    client.force_login(acme_member)
    resp = client.delete(f"/api/contacts/{c.id}/assets/{a.id}/")
    assert resp.status_code == 204
    assert not AssetOwner.objects.filter(contact=c, asset=a).exists()


@pytest.mark.django_db
def test_remove_nonexistent_returns_404(client, acme_member, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    client.force_login(acme_member)
    resp = client.delete(f"/api/contacts/{c.id}/assets/{a.id}/")
    assert resp.status_code == 404


# ── cascade ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_contact_cascades_to_asset_owner(db, acme):
    c = make_contact(acme)
    a = make_asset(acme)
    ow = AssetOwner.objects.create(contact=c, asset=a)
    c.delete()
    assert not AssetOwner.objects.filter(pk=ow.pk).exists()


@pytest.mark.django_db
def test_is_active_and_last_seen_at_returned_in_list(client, acme_member, acme):
    from django.utils import timezone
    c = make_contact(acme)
    a = Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, name="h1", agent_name="h1",
        is_active=False, last_seen_at=timezone.now(),
    )
    AssetOwner.objects.create(contact=c, asset=a)
    client.force_login(acme_member)
    data = client.get(f"/api/contacts/{c.id}/assets/").json()
    assert len(data) == 1
