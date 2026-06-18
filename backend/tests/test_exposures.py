"""Unit tests for the exposure resolver (PRD #536).

Covers: host_exposures, annotate_internet_facing — pure domain logic.
"""
import pytest
from incidents.models import Asset, NatExposure
from incidents.services.exposures import annotate_internet_facing, host_exposures
from ingress.models import Route
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


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
def route(acme, host):
    return Route.objects.create(
        fqdn="app.acme.com",
        backend_host="10.0.0.1",
        backend_port=443,
        organization=acme,
        status=Route.STATUS_ACTIVE,
        backend_asset=host,
    )


@pytest.fixture
def nat(host):
    return NatExposure.objects.create(
        asset=host,
        protocol=NatExposure.PROTOCOL_TCP,
        port=3389,
    )


# ── host_exposures ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_host_with_no_exposures_returns_empty(host):
    assert host_exposures(host) == []


@pytest.mark.django_db
def test_host_with_route_exposure(host, route):
    exposures = host_exposures(host)
    assert len(exposures) == 1
    e = exposures[0]
    assert e.kind == "ingress_route"
    assert e.protection == "protected"
    assert e.specifics["fqdn"] == "app.acme.com"
    assert e.specifics["backend_port"] == 443


@pytest.mark.django_db
def test_host_with_nat_exposure(host, nat):
    exposures = host_exposures(host)
    assert len(exposures) == 1
    e = exposures[0]
    assert e.kind == "direct_nat"
    assert e.protection == "raw"
    assert e.specifics["protocol"] == "tcp"
    assert e.specifics["port"] == 3389
    assert e.specifics["public_ip"] is None


@pytest.mark.django_db
def test_host_with_nat_exposure_public_ip(host):
    nat = NatExposure.objects.create(
        asset=host,
        protocol=NatExposure.PROTOCOL_UDP,
        port=500,
        public_ip="1.2.3.4",
        description="IKE VPN",
    )
    exposures = host_exposures(host)
    assert len(exposures) == 1
    e = exposures[0]
    assert e.specifics["public_ip"] == "1.2.3.4"
    assert e.specifics["description"] == "IKE VPN"


@pytest.mark.django_db
def test_host_with_both_route_and_nat(host, route, nat):
    exposures = host_exposures(host)
    kinds = [e.kind for e in exposures]
    assert "ingress_route" in kinds
    assert "direct_nat" in kinds
    assert len(exposures) == 2


@pytest.mark.django_db
def test_multiple_nat_exposures_all_returned(host):
    NatExposure.objects.create(asset=host, protocol="tcp", port=80)
    NatExposure.objects.create(asset=host, protocol="tcp", port=443)
    exposures = host_exposures(host)
    ports = {e.specifics["port"] for e in exposures}
    assert ports == {80, 443}


# ── annotate_internet_facing ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_annotate_marks_host_with_route_as_internet_facing(host, route):
    qs = annotate_internet_facing(Asset.objects.filter(pk=host.pk))
    assert qs.get().internet_facing is True


@pytest.mark.django_db
def test_annotate_marks_host_with_nat_as_internet_facing(host, nat):
    qs = annotate_internet_facing(Asset.objects.filter(pk=host.pk))
    assert qs.get().internet_facing is True


@pytest.mark.django_db
def test_annotate_marks_host_without_exposure_as_not_internet_facing(host):
    qs = annotate_internet_facing(Asset.objects.filter(pk=host.pk))
    assert qs.get().internet_facing is False


@pytest.mark.django_db
def test_annotate_does_not_mark_route_asset_as_internet_facing(acme):
    r = Route.objects.create(
        fqdn="other.acme.com",
        backend_host="10.0.0.5",
        backend_port=80,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )
    route_asset = Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_ROUTE,
        name="other.acme.com",
        route=r,
    )
    qs = annotate_internet_facing(Asset.objects.filter(pk=route_asset.pk))
    assert qs.get().internet_facing is False


@pytest.mark.django_db
def test_annotate_filter_internet_facing_true_excludes_unexposed(host, route, acme):
    other = Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, name="plain", agent_name="plain"
    )
    exposed_ids = set(
        annotate_internet_facing(Asset.objects.filter(organization=acme))
        .filter(internet_facing=True)
        .values_list("pk", flat=True)
    )
    assert host.pk in exposed_ids
    assert other.pk not in exposed_ids
