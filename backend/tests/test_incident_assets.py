import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Asset, Incident, IncidentAsset
from incidents.services.assets import link_asset_from_source_ref


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


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


def make_incident(org, display_id=None, source_kind="manual", source_ref=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Test",
        tlp="amber",
        display_id=display_id or f"INC-2026-A{count + 1:03d}",
        source_kind=source_kind,
        source_ref=source_ref or {},
    )


# ── auto-link service ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_link_asset_wazuh_event_creates_host_asset(acme):
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "web01", "ip_address": "10.0.0.1"})
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)

    assert Asset.objects.filter(organization=acme, kind="host", agent_name="web01").count() == 1
    asset = Asset.objects.get(organization=acme, kind="host", agent_name="web01")
    assert asset.name == "web01"
    assert asset.ip_address == "10.0.0.1"
    assert IncidentAsset.objects.filter(incident=inc, asset=asset, added_by=None).exists()


@pytest.mark.django_db
def test_link_asset_agent_finding_creates_host_asset(acme):
    inc = make_incident(acme, source_kind="agent_finding", source_ref={"agent": {"name": "db01", "ip": "10.0.0.2"}})
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)

    assert Asset.objects.filter(organization=acme, kind="host", agent_name="db01").exists()


@pytest.mark.django_db
def test_link_asset_idempotent(acme):
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "web01"})
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)

    assert Asset.objects.filter(organization=acme, kind="host", agent_name="web01").count() == 1
    assert IncidentAsset.objects.filter(incident=inc).count() == 1


@pytest.mark.django_db
def test_link_asset_reuses_existing_asset_across_incidents(acme):
    inc1 = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "web01"})
    inc2 = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "web01"})
    link_asset_from_source_ref(inc1, inc1.source_kind, inc1.source_ref)
    link_asset_from_source_ref(inc2, inc2.source_kind, inc2.source_ref)

    assert Asset.objects.filter(organization=acme, kind="host", agent_name="web01").count() == 1
    asset = Asset.objects.get(organization=acme, kind="host", agent_name="web01")
    assert IncidentAsset.objects.filter(asset=asset).count() == 2


@pytest.mark.django_db
def test_link_asset_noop_for_manual_source(acme):
    inc = make_incident(acme, source_kind="manual")
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)

    assert Asset.objects.count() == 0
    assert IncidentAsset.objects.count() == 0


@pytest.mark.django_db
def test_link_asset_noop_when_agent_name_missing(acme):
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"rule": {"id": "1234"}})
    link_asset_from_source_ref(inc, inc.source_kind, inc.source_ref)

    assert Asset.objects.count() == 0


@pytest.mark.django_db
def test_link_asset_noop_when_source_ref_is_string(acme):
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={})
    link_asset_from_source_ref(inc, inc.source_kind, "some-string-ref")

    assert Asset.objects.count() == 0


# ── GET /api/assets/ ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_asset_list_requires_auth(client, acme):
    response = client.get("/api/assets/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_asset_list_org_isolation(client, acme_member, acme, contoso):
    own = Asset.objects.create(organization=acme, kind="host", name="own", agent_name="own")
    other = Asset.objects.create(organization=contoso, kind="host", name="other", agent_name="other")
    client.force_login(acme_member)
    response = client.get("/api/assets/")
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert own.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_asset_list_staff_sees_all(client, staff, acme, contoso):
    a1 = Asset.objects.create(organization=acme, kind="host", name="a1", agent_name="a1")
    a2 = Asset.objects.create(organization=contoso, kind="host", name="a2", agent_name="a2")
    client.force_login(staff)
    response = client.get("/api/assets/")
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert a1.id in ids
    assert a2.id in ids


@pytest.mark.django_db
def test_asset_list_search_by_name(client, staff, acme):
    Asset.objects.create(organization=acme, kind="host", name="webserver", agent_name="web01")
    Asset.objects.create(organization=acme, kind="host", name="database", agent_name="db01")
    client.force_login(staff)
    response = client.get("/api/assets/?q=web")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "webserver"


# ── POST /api/assets/ ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_asset_create_host(client, staff, acme):
    client.force_login(staff)
    response = client.post(
        "/api/assets/",
        {"kind": "host", "organization": "acme", "name": "web01", "agent_name": "web01", "ip_address": "1.2.3.4"},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["kind"] == "host"
    assert data["agent_name"] == "web01"
    assert data["ip_address"] == "1.2.3.4"


@pytest.mark.django_db
def test_asset_create_host_duplicate_rejected(client, staff, acme):
    Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    client.force_login(staff)
    response = client.post(
        "/api/assets/",
        {"kind": "host", "organization": "acme", "name": "web01", "agent_name": "web01"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_asset_create_member_forbidden_for_other_org(client, acme_member, contoso):
    client.force_login(acme_member)
    response = client.post(
        "/api/assets/",
        {"kind": "host", "organization": "contoso", "name": "web01", "agent_name": "web01"},
        content_type="application/json",
    )
    assert response.status_code == 403


# ── POST /api/incidents/{id}/assets/ ─────────────────────────────────────────


@pytest.mark.django_db
def test_incident_asset_link(client, staff, acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": asset.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["asset"]["id"] == asset.id
    assert data["added_by_username"] == "staff"
    assert data["added_by"] is not None


@pytest.mark.django_db
def test_incident_asset_link_appears_in_detail(client, staff, acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    IncidentAsset.objects.create(incident=inc, asset=asset, added_by=None)

    client.force_login(staff)
    response = client.get(f"/api/incidents/{inc.display_id}/")
    assert response.status_code == 200
    assets = response.json()["assets"]
    assert len(assets) == 1
    assert assets[0]["asset"]["id"] == asset.id
    assert assets[0]["added_by"] is None
    assert assets[0]["added_by_username"] is None


@pytest.mark.django_db
def test_incident_asset_link_duplicate_rejected(client, staff, acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    IncidentAsset.objects.create(incident=inc, asset=asset, added_by=None)
    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": asset.id},
        content_type="application/json",
    )
    assert response.status_code == 400


# ── DELETE /api/incidents/{id}/assets/{asset_id}/ ────────────────────────────


@pytest.mark.django_db
def test_incident_asset_unlink(client, staff, acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    IncidentAsset.objects.create(incident=inc, asset=asset, added_by=None)
    client.force_login(staff)
    response = client.delete(f"/api/incidents/{inc.display_id}/assets/{asset.id}/")
    assert response.status_code == 204
    assert not IncidentAsset.objects.filter(incident=inc, asset=asset).exists()
    assert Asset.objects.filter(pk=asset.id).exists()


@pytest.mark.django_db
def test_incident_asset_unlink_not_linked_returns_404(client, staff, acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    client.force_login(staff)
    response = client.delete(f"/api/incidents/{inc.display_id}/assets/{asset.id}/")
    assert response.status_code == 404


# ── route-asset fan-out (PRD #563) ───────────────────────────────────────────


def _make_route(org, fqdn):
    from ingress.models import Route
    return Route.objects.create(
        organization=org, fqdn=fqdn, backend_host="10.0.0.9", backend_port=8080,
    )


@pytest.mark.django_db
def test_link_route_asset_fans_out_to_siblings(client, staff, acme):
    inc = make_incident(acme)
    route = _make_route(acme, "app.acme.test")
    route_asset = Asset.objects.create(organization=acme, kind="route", name="app", route=route)
    behind1 = Asset.objects.create(organization=acme, kind="host", name="h1", agent_name="h1", route=route)
    behind2 = Asset.objects.create(organization=acme, kind="host", name="h2", agent_name="h2", route=route)
    unrelated = Asset.objects.create(organization=acme, kind="host", name="h3", agent_name="h3")

    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": route_asset.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    # response is the directly-linked (route) asset
    assert response.json()["asset"]["id"] == route_asset.id

    linked_ids = set(IncidentAsset.objects.filter(incident=inc).values_list("asset_id", flat=True))
    assert linked_ids == {route_asset.id, behind1.id, behind2.id}
    assert unrelated.id not in linked_ids


@pytest.mark.django_db
def test_link_route_asset_is_idempotent_over_siblings(client, staff, acme):
    inc = make_incident(acme)
    route = _make_route(acme, "app.acme.test")
    route_asset = Asset.objects.create(organization=acme, kind="route", name="app", route=route)
    behind = Asset.objects.create(organization=acme, kind="host", name="h1", agent_name="h1", route=route)
    # pre-link a sibling
    IncidentAsset.objects.create(incident=inc, asset=behind, added_by=None)

    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": route_asset.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    # no duplicate link rows; both end up linked exactly once
    assert IncidentAsset.objects.filter(incident=inc, asset=behind).count() == 1
    assert IncidentAsset.objects.filter(incident=inc, asset=route_asset).count() == 1


@pytest.mark.django_db
def test_link_route_asset_respects_org_isolation(client, staff, acme, contoso):
    inc = make_incident(acme)
    route = _make_route(acme, "app.acme.test")
    route_asset = Asset.objects.create(organization=acme, kind="route", name="app", route=route)
    acme_behind = Asset.objects.create(organization=acme, kind="host", name="h1", agent_name="h1", route=route)
    # a foreign-org asset that happens to point at the same route must NOT be linked
    contoso_behind = Asset.objects.create(organization=contoso, kind="host", name="x1", agent_name="x1", route=route)

    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": route_asset.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    linked_ids = set(IncidentAsset.objects.filter(incident=inc).values_list("asset_id", flat=True))
    assert acme_behind.id in linked_ids
    assert contoso_behind.id not in linked_ids


@pytest.mark.django_db
def test_link_host_asset_does_not_fan_out(client, staff, acme):
    inc = make_incident(acme)
    route = _make_route(acme, "app.acme.test")
    host = Asset.objects.create(organization=acme, kind="host", name="h1", agent_name="h1", route=route)
    other_behind = Asset.objects.create(organization=acme, kind="host", name="h2", agent_name="h2", route=route)

    client.force_login(staff)
    response = client.post(
        f"/api/incidents/{inc.display_id}/assets/",
        {"asset": host.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    linked_ids = set(IncidentAsset.objects.filter(incident=inc).values_list("asset_id", flat=True))
    assert linked_ids == {host.id}
    assert other_behind.id not in linked_ids
