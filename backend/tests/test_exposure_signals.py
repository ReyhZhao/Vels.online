"""Integration tests for Route↔Asset auto-linking signals (PRD #536)."""
import pytest
from incidents.models import Asset
from ingress.models import Route
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def make_host(org, name="srv-01", ip="10.0.0.1", agent_name=None):
    return Asset.objects.create(
        organization=org,
        kind=Asset.KIND_HOST,
        name=name,
        agent_name=agent_name or name,
        ip_address=ip,
    )


def make_route(org, backend_host="10.0.0.1", fqdn="app.acme.com"):
    return Route.objects.create(
        fqdn=fqdn,
        backend_host=backend_host,
        backend_port=443,
        organization=org,
        status=Route.STATUS_ACTIVE,
    )


# ── Route saved first, asset exists → signal auto-links ───────────────────────


@pytest.mark.django_db
def test_route_save_links_unambiguous_ip_match(acme):
    host = make_host(acme, ip="10.0.0.5")
    route = make_route(acme, backend_host="10.0.0.5")

    route.refresh_from_db()
    assert route.backend_asset_id == host.pk


@pytest.mark.django_db
def test_route_save_no_match_leaves_unlinked(acme):
    make_host(acme, ip="10.0.0.1")
    route = make_route(acme, backend_host="10.0.0.99")

    route.refresh_from_db()
    assert route.backend_asset_id is None


@pytest.mark.django_db
def test_route_save_ambiguous_ip_leaves_unlinked(acme):
    make_host(acme, name="a", agent_name="a", ip="10.0.0.1")
    make_host(acme, name="b", agent_name="b", ip="10.0.0.1")
    route = make_route(acme, backend_host="10.0.0.1")

    route.refresh_from_db()
    assert route.backend_asset_id is None


@pytest.mark.django_db
def test_route_save_does_not_overwrite_existing_link(acme):
    host_a = make_host(acme, name="a", agent_name="a", ip="10.0.0.1")
    host_b = make_host(acme, name="b", agent_name="b", ip="10.0.0.2")
    route = Route.objects.create(
        fqdn="app.acme.com",
        backend_host="10.0.0.2",
        backend_port=443,
        organization=acme,
        status=Route.STATUS_ACTIVE,
        backend_asset=host_a,
    )
    route.refresh_from_db()
    # Existing manual link (host_a) must not be replaced by auto-match (host_b)
    assert route.backend_asset_id == host_a.pk


# ── Asset created after route → signal backfills ───────────────────────────────


@pytest.mark.django_db
def test_asset_create_backfills_existing_unlinked_route(acme):
    route = make_route(acme, backend_host="10.0.0.7")
    assert route.backend_asset_id is None

    host = make_host(acme, ip="10.0.0.7")

    route.refresh_from_db()
    assert route.backend_asset_id == host.pk


@pytest.mark.django_db
def test_asset_ip_change_backfills_route(acme):
    host = make_host(acme, ip="10.0.0.1")
    route = make_route(acme, backend_host="10.0.0.50")
    route.refresh_from_db()
    assert route.backend_asset_id is None

    host.ip_address = "10.0.0.50"
    host.save(update_fields=["ip_address"])

    route.refresh_from_db()
    assert route.backend_asset_id == host.pk


# ── Derived-on-read: exposure reflects current link state ─────────────────────


@pytest.mark.django_db
def test_deleting_route_removes_exposure_on_next_read(acme):
    from incidents.services.exposures import host_exposures

    host = make_host(acme, ip="10.0.0.1")
    route = make_route(acme, backend_host="10.0.0.1")
    route.refresh_from_db()
    assert route.backend_asset_id == host.pk

    # Exposure is present
    assert len(host_exposures(host)) == 1

    # Deleting the route removes the exposure on next read (derived, not stored)
    route.delete()
    assert host_exposures(host) == []


@pytest.mark.django_db
def test_manual_override_to_different_host_persists(acme):
    from incidents.services.exposures import host_exposures

    host_a = make_host(acme, name="a", agent_name="a", ip="10.0.0.1")
    host_b = make_host(acme, name="b", agent_name="b", ip="10.0.0.2")

    # Route initially points to host_a's IP but is manually set to host_b
    route = Route.objects.create(
        fqdn="app.acme.com",
        backend_host="10.0.0.1",
        backend_port=443,
        organization=acme,
        status=Route.STATUS_ACTIVE,
        backend_asset=host_b,  # manual override
    )
    route.refresh_from_db()
    # Manual link to host_b must be preserved (not overwritten by auto-match to host_a)
    assert route.backend_asset_id == host_b.pk

    # Exposure belongs to host_b
    assert any(e.specifics.get("fqdn") == "app.acme.com" for e in host_exposures(host_b))
    assert host_exposures(host_a) == []


# ── Netbird routes are not auto-linked ────────────────────────────────────────


@pytest.mark.django_db
def test_netbird_route_not_auto_linked(acme):
    make_host(acme, ip="10.0.0.1")
    route = Route.objects.create(
        fqdn="nb.acme.com",
        backend_host="10.0.0.1",
        backend_port=443,
        organization=acme,
        status=Route.STATUS_ACTIVE,
        backend_type=Route.TYPE_NETBIRD,
    )
    route.refresh_from_db()
    assert route.backend_asset_id is None
