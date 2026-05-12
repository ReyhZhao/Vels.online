from unittest.mock import patch

import pytest

from ingress.models import Route
from security.models import Organization, OrganizationMembership

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


BW_SERVICES = [
    {"server_name": "a.example.com", "backend_host": "10.0.0.1", "backend_port": 80, "backend_protocol": "http"},
    {"server_name": "b.example.com", "backend_host": "10.0.0.2", "backend_port": 443, "backend_protocol": "https"},
]

# ── GET /api/ingress/routes/import/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_import_get_requires_auth(client, acme):
    assert client.get("/api/ingress/routes/import/?org=acme").status_code == 401


@pytest.mark.django_db
def test_import_get_non_staff_forbidden(client, acme_member):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/import/?org=acme").status_code == 403


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_get_returns_candidates(MockClient, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.get("/api/ingress/routes/import/?org=acme")
    assert res.status_code == 200
    fqdns = [c["server_name"] for c in res.json()["candidates"]]
    assert "a.example.com" in fqdns
    assert "b.example.com" in fqdns


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_get_excludes_existing_routes(MockClient, client, staff, acme):
    Route.objects.create(
        fqdn="a.example.com",
        backend_host="10.0.0.1",
        backend_port=80,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.get("/api/ingress/routes/import/?org=acme")
    assert res.status_code == 200
    fqdns = [c["server_name"] for c in res.json()["candidates"]]
    assert "a.example.com" not in fqdns
    assert "b.example.com" in fqdns


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_get_excludes_routes_from_other_orgs(MockClient, client, staff, acme, db):
    other = Organization.objects.create(name="Other", slug="other", wazuh_group="other")
    Route.objects.create(
        fqdn="a.example.com",
        backend_host="10.0.0.1",
        backend_port=80,
        organization=other,
        status=Route.STATUS_ACTIVE,
    )
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.get("/api/ingress/routes/import/?org=acme")
    assert res.status_code == 200
    fqdns = [c["server_name"] for c in res.json()["candidates"]]
    assert "a.example.com" not in fqdns


# ── POST /api/ingress/routes/import/ ─────────────────────────────────────────


@pytest.mark.django_db
def test_import_post_requires_auth(client, acme):
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 401


@pytest.mark.django_db
def test_import_post_non_staff_forbidden(client, acme_member):
    client.force_login(acme_member)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
@patch("ingress.views.check_route_dns")
@patch("ingress.views.BunkerWebClient")
def test_import_post_happy_path(MockClient, mock_dns, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com", "b.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 201
    data = res.json()
    assert len(data) == 2
    fqdns = {r["fqdn"] for r in data}
    assert fqdns == {"a.example.com", "b.example.com"}
    for r in data:
        assert r["status"] == "active"
    assert Route.objects.filter(organization=acme).count() == 2
    assert mock_dns.delay.call_count == 2


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_does_not_call_create_service(MockClient, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com"]},
        content_type="application/json",
    )
    MockClient.return_value.create_service.assert_not_called()


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_backend_type_is_direct(MockClient, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com"]},
        content_type="application/json",
    )
    route = Route.objects.get(fqdn="a.example.com")
    assert route.backend_type == Route.TYPE_DIRECT


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_unknown_fqdn_returns_400(MockClient, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["unknown.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "unknown.example.com" in res.json()["detail"]


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_already_imported_returns_409(MockClient, client, staff, acme):
    Route.objects.create(
        fqdn="a.example.com",
        backend_host="10.0.0.1",
        backend_port=80,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 409


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_quota_exceeded_returns_403(MockClient, client, staff, acme):
    acme.max_routes = 1
    acme.save()
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": ["a.example.com", "b.example.com"]},
        content_type="application/json",
    )
    assert res.status_code == 403
    assert "quota" in res.json()["detail"].lower()
    assert Route.objects.filter(organization=acme).count() == 0


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_import_post_empty_fqdns_returns_400(MockClient, client, staff, acme):
    MockClient.return_value.list_services.return_value = BW_SERVICES
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/import/?org=acme",
        {"fqdns": []},
        content_type="application/json",
    )
    assert res.status_code == 400
