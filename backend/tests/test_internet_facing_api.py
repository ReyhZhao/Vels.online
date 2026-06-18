"""Tests for internet_facing field + filter on AssetSerializer / AssetListView (PRD #536)."""
import pytest
from incidents.models import Asset, NatExposure
from ingress.models import Route
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


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
def exposed_host(acme):
    h = Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="web-01",
        agent_name="web-01",
        ip_address="10.0.0.2",
    )
    NatExposure.objects.create(asset=h, protocol="tcp", port=443)
    return h


# ── AssetSerializer internet_facing + exposures ───────────────────────────────


@pytest.mark.django_db
def test_asset_serializer_internet_facing_false_when_no_exposure(client, staff, host):
    client.force_login(staff)
    resp = client.get(f"/api/assets/{host.pk}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["internet_facing"] is False
    assert data["exposures"] == []


@pytest.mark.django_db
def test_asset_serializer_internet_facing_true_with_nat(client, staff, exposed_host):
    client.force_login(staff)
    resp = client.get(f"/api/assets/{exposed_host.pk}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["internet_facing"] is True
    assert len(data["exposures"]) == 1
    exp = data["exposures"][0]
    assert exp["kind"] == "direct_nat"
    assert exp["protection"] == "raw"
    assert exp["specifics"]["port"] == 443


@pytest.mark.django_db
def test_asset_serializer_ingress_route_exposure(client, staff, host, acme):
    route = Route.objects.create(
        fqdn="app.acme.com",
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=acme,
        status=Route.STATUS_ACTIVE,
        backend_asset=host,
    )
    client.force_login(staff)
    resp = client.get(f"/api/assets/{host.pk}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["internet_facing"] is True
    exp = data["exposures"][0]
    assert exp["kind"] == "ingress_route"
    assert exp["protection"] == "protected"
    assert exp["specifics"]["fqdn"] == "app.acme.com"


# ── AssetFilterSet internet_facing filter ─────────────────────────────────────


@pytest.mark.django_db
def test_filter_internet_facing_true_returns_exposed_hosts(client, staff, host, exposed_host, acme):
    client.force_login(staff)
    resp = client.get(f"/api/assets/?org=acme&internet_facing=true")
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert exposed_host.pk in ids
    assert host.pk not in ids


@pytest.mark.django_db
def test_filter_internet_facing_false_returns_unexposed_hosts(client, staff, host, exposed_host, acme):
    client.force_login(staff)
    resp = client.get(f"/api/assets/?org=acme&internet_facing=false")
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert host.pk in ids
    assert exposed_host.pk not in ids
