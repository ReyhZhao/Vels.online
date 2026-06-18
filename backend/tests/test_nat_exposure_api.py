"""API tests for NAT exposure CRUD (PRD #536)."""
import pytest
from incidents.models import Asset, NatExposure
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def host(acme):
    return Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="srv-01",
        agent_name="srv-01",
        ip_address="10.0.0.1",
    )


@pytest.fixture
def nat(host):
    return NatExposure.objects.create(
        asset=host,
        protocol="tcp",
        port=3389,
        description="RDP",
    )


# ── GET /api/assets/<pk>/nat-exposures/ ───────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client, host):
    assert client.get(f"/api/assets/{host.pk}/nat-exposures/").status_code == 401


@pytest.mark.django_db
def test_list_returns_nats_for_host(client, acme_member, host, nat):
    client.force_login(acme_member)
    resp = client.get(f"/api/assets/{host.pk}/nat-exposures/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["port"] == 3389
    assert data[0]["protocol"] == "tcp"


@pytest.mark.django_db
def test_list_empty_when_no_nats(client, acme_member, host):
    client.force_login(acme_member)
    resp = client.get(f"/api/assets/{host.pk}/nat-exposures/")
    assert resp.status_code == 200
    assert resp.json() == []


# ── POST /api/assets/<pk>/nat-exposures/ ──────────────────────────────────────


@pytest.mark.django_db
def test_create_nat_exposure(client, acme_member, host):
    client.force_login(acme_member)
    resp = client.post(
        f"/api/assets/{host.pk}/nat-exposures/",
        {"protocol": "tcp", "port": 22, "description": "SSH"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["port"] == 22
    assert NatExposure.objects.filter(asset=host, port=22).exists()


@pytest.mark.django_db
def test_create_nat_requires_auth(client, host):
    resp = client.post(
        f"/api/assets/{host.pk}/nat-exposures/",
        {"protocol": "tcp", "port": 22},
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_create_nat_on_route_asset_rejected(client, staff, acme):
    from ingress.models import Route
    route = Route.objects.create(
        fqdn="app.acme.com", backend_host="1.1.1.1", backend_port=80, organization=acme
    )
    route_asset = Asset.objects.create(
        organization=acme, kind=Asset.KIND_ROUTE, name="app.acme.com", route=route
    )
    client.force_login(staff)
    resp = client.post(
        f"/api/assets/{route_asset.pk}/nat-exposures/",
        {"protocol": "tcp", "port": 80},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── PATCH /api/assets/<pk>/nat-exposures/<nat_pk>/ ────────────────────────────


@pytest.mark.django_db
def test_patch_nat_exposure(client, acme_member, host, nat):
    client.force_login(acme_member)
    resp = client.patch(
        f"/api/assets/{host.pk}/nat-exposures/{nat.pk}/",
        {"port": 4444},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["port"] == 4444
    nat.refresh_from_db()
    assert nat.port == 4444


# ── DELETE /api/assets/<pk>/nat-exposures/<nat_pk>/ ──────────────────────────


@pytest.mark.django_db
def test_delete_nat_exposure(client, acme_member, host, nat):
    client.force_login(acme_member)
    resp = client.delete(f"/api/assets/{host.pk}/nat-exposures/{nat.pk}/")
    assert resp.status_code == 204
    assert not NatExposure.objects.filter(pk=nat.pk).exists()


@pytest.mark.django_db
def test_delete_nat_not_found(client, acme_member, host):
    client.force_login(acme_member)
    resp = client.delete(f"/api/assets/{host.pk}/nat-exposures/9999/")
    assert resp.status_code == 404
