from unittest.mock import patch

import pytest

from ingress.bunkerweb import BunkerWebError
from ingress.models import Route
from security.models import Organization, OrganizationMembership

# ── fixtures ────────────────────────────────────────────────────────────────


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


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


def make_route(org, fqdn="app.example.com", **kwargs):
    return Route.objects.create(
        fqdn=fqdn,
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=org,
        status=Route.STATUS_ACTIVE,
        **kwargs,
    )


CREATE_PAYLOAD = {
    "fqdn": "new.example.com",
    "backend_host": "10.0.0.2",
    "backend_port": 3000,
    "backend_protocol": "http",
}

# ── GET /api/ingress/routes/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client, acme):
    assert client.get("/api/ingress/routes/?org=acme").status_code == 401


@pytest.mark.django_db
def test_list_non_member_forbidden(client, alice, acme):
    client.force_login(alice)
    assert client.get("/api/ingress/routes/?org=acme").status_code == 403


@pytest.mark.django_db
def test_list_unknown_org_returns_404(client, acme_member):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/?org=nope").status_code == 404


@pytest.mark.django_db
def test_list_returns_org_routes(client, acme_member, acme, contoso):
    own = make_route(acme, fqdn="own.example.com")
    other = make_route(contoso, fqdn="other.example.com")
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/?org=acme")
    assert res.status_code == 200
    fqdns = [r["fqdn"] for r in res.json()]
    assert own.fqdn in fqdns
    assert other.fqdn not in fqdns


@pytest.mark.django_db
def test_list_staff_can_view_any_org(client, staff, contoso):
    make_route(contoso, fqdn="ct.example.com")
    client.force_login(staff)
    res = client.get("/api/ingress/routes/?org=contoso")
    assert res.status_code == 200
    assert len(res.json()) == 1


# ── POST /api/ingress/routes/ ────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_requires_auth(client, acme):
    assert (
        client.post(
            "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
        ).status_code
        == 401
    )


@pytest.mark.django_db
def test_create_non_member_forbidden(client, alice, acme):
    client.force_login(alice)
    assert (
        client.post(
            "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_create_success(MockClient, client, acme_member, acme):
    MockClient.return_value.create_service.return_value = {}
    client.force_login(acme_member)
    res = client.post(
        "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
    )
    assert res.status_code == 201
    data = res.json()
    assert data["fqdn"] == "new.example.com"
    assert data["status"] == "active"
    assert Route.objects.filter(fqdn="new.example.com").exists()
    MockClient.return_value.create_service.assert_called_once_with(
        "new.example.com", "10.0.0.2", 3000, "http"
    )


@pytest.mark.django_db
def test_create_duplicate_fqdn_returns_409(client, acme_member, acme):
    make_route(acme, fqdn="new.example.com")
    client.force_login(acme_member)
    res = client.post(
        "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
    )
    assert res.status_code == 409


@pytest.mark.django_db
def test_create_quota_exceeded_returns_403(client, acme_member, acme):
    acme.max_routes = 1
    acme.save()
    make_route(acme, fqdn="existing.example.com")
    client.force_login(acme_member)
    res = client.post(
        "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
    )
    assert res.status_code == 403
    assert "quota" in res.json()["detail"].lower()


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_create_bunkerweb_error_rolls_back(MockClient, client, acme_member, acme):
    MockClient.return_value.create_service.side_effect = BunkerWebError(500, "internal error")
    client.force_login(acme_member)
    res = client.post(
        "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
    )
    assert res.status_code == 502
    assert not Route.objects.filter(fqdn="new.example.com").exists()


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_create_staff_bypass(MockClient, client, staff, acme):
    MockClient.return_value.create_service.return_value = {}
    client.force_login(staff)
    res = client.post(
        "/api/ingress/routes/?org=acme", CREATE_PAYLOAD, content_type="application/json"
    )
    assert res.status_code == 201


# ── GET /api/ingress/routes/<fqdn>/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_detail_requires_auth(client, acme):
    make_route(acme)
    assert client.get("/api/ingress/routes/app.example.com/").status_code == 401


@pytest.mark.django_db
def test_detail_non_member_forbidden(client, alice, acme):
    make_route(acme)
    client.force_login(alice)
    assert client.get("/api/ingress/routes/app.example.com/").status_code == 403


@pytest.mark.django_db
def test_detail_returns_route(client, acme_member, acme):
    make_route(acme)
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/")
    assert res.status_code == 200
    assert res.json()["fqdn"] == "app.example.com"


@pytest.mark.django_db
def test_detail_not_found(client, acme_member):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/missing.example.com/").status_code == 404


@pytest.mark.django_db
def test_detail_staff_can_view_any_org(client, staff, contoso):
    make_route(contoso)
    client.force_login(staff)
    assert client.get("/api/ingress/routes/app.example.com/").status_code == 200


# ── DELETE /api/ingress/routes/<fqdn>/ ───────────────────────────────────────


@pytest.mark.django_db
def test_delete_requires_auth(client, acme):
    make_route(acme)
    assert client.delete("/api/ingress/routes/app.example.com/").status_code == 401


@pytest.mark.django_db
def test_delete_non_member_forbidden(client, alice, acme):
    make_route(acme)
    client.force_login(alice)
    assert client.delete("/api/ingress/routes/app.example.com/").status_code == 403


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_delete_success(MockClient, client, acme_member, acme):
    make_route(acme)
    MockClient.return_value.delete_service.return_value = None
    client.force_login(acme_member)
    res = client.delete("/api/ingress/routes/app.example.com/")
    assert res.status_code == 204
    assert not Route.objects.filter(fqdn="app.example.com").exists()
    MockClient.return_value.delete_service.assert_called_once_with("app.example.com")


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_delete_bunkerweb_error_keeps_record(MockClient, client, acme_member, acme):
    make_route(acme)
    MockClient.return_value.delete_service.side_effect = BunkerWebError(500, "error")
    client.force_login(acme_member)
    res = client.delete("/api/ingress/routes/app.example.com/")
    assert res.status_code == 502
    assert Route.objects.filter(fqdn="app.example.com").exists()


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_delete_staff_bypass(MockClient, client, staff, contoso):
    make_route(contoso)
    MockClient.return_value.delete_service.return_value = None
    client.force_login(staff)
    assert client.delete("/api/ingress/routes/app.example.com/").status_code == 204


# ── GET /api/ingress/settings/ ───────────────────────────────────────────────


@pytest.mark.django_db
def test_settings_returns_bunkerweb_ip(client, acme_member, settings):
    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    settings.BUNKERWEB_PUBLIC_FQDN = ""
    client.force_login(acme_member)
    res = client.get("/api/ingress/settings/")
    assert res.status_code == 200
    assert res.json()["bunkerweb_public_ip"] == "203.0.113.42"
    assert res.json()["bunkerweb_public_fqdn"] == ""


@pytest.mark.django_db
def test_settings_returns_bunkerweb_fqdn(client, acme_member, settings):
    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    settings.BUNKERWEB_PUBLIC_FQDN = "bw.example.com"
    client.force_login(acme_member)
    res = client.get("/api/ingress/settings/")
    assert res.status_code == 200
    assert res.json()["bunkerweb_public_fqdn"] == "bw.example.com"
