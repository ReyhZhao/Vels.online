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
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def route(acme):
    return Route.objects.create(
        fqdn="app.example.com",
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )


BW_SETTINGS = {
    "USE_MODSECURITY": "yes",
    "USE_MODSECURITY_CRS": "no",
    "MODSECURITY_CRS_PARANOIA_LEVEL": "2",
    "SOME_OTHER_KEY": "value",
}

# ── GET /api/ingress/routes/<fqdn>/settings/ ─────────────────────────────────


@pytest.mark.django_db
def test_get_settings_requires_auth(client, route):
    assert client.get("/api/ingress/routes/app.example.com/settings/").status_code == 401


@pytest.mark.django_db
def test_get_settings_non_member_forbidden(client, alice, route):
    client.force_login(alice)
    assert client.get("/api/ingress/routes/app.example.com/settings/").status_code == 403


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_get_settings_returns_filtered_waf_keys(MockBW, client, acme_member, route):
    MockBW.return_value.get_service_settings.return_value = BW_SETTINGS
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/settings/")
    assert res.status_code == 200
    data = res.json()
    assert data["USE_MODSECURITY"] == "yes"
    assert data["USE_MODSECURITY_CRS"] == "no"
    assert data["MODSECURITY_CRS_PARANOIA_LEVEL"] == "2"
    assert "SOME_OTHER_KEY" not in data


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_get_settings_bunkerweb_error_returns_502(MockBW, client, acme_member, route):
    MockBW.return_value.get_service_settings.side_effect = BunkerWebError(500, "error")
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/app.example.com/settings/").status_code == 502


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_get_settings_staff_bypass(MockBW, client, route, django_user_model):
    staff = django_user_model.objects.create_user(username="s", password="p", is_staff=True)
    MockBW.return_value.get_service_settings.return_value = BW_SETTINGS
    client.force_login(staff)
    assert client.get("/api/ingress/routes/app.example.com/settings/").status_code == 200


# ── PATCH /api/ingress/routes/<fqdn>/settings/ ───────────────────────────────


@pytest.mark.django_db
def test_patch_settings_requires_auth(client, route):
    assert (
        client.patch(
            "/api/ingress/routes/app.example.com/settings/",
            {"USE_MODSECURITY": "yes"},
            content_type="application/json",
        ).status_code
        == 401
    )


@pytest.mark.django_db
def test_patch_settings_non_member_forbidden(client, alice, route):
    client.force_login(alice)
    assert (
        client.patch(
            "/api/ingress/routes/app.example.com/settings/",
            {"USE_MODSECURITY": "yes"},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
@patch("ingress.views.push_route_settings")
def test_patch_settings_dispatches_task_and_returns_payload(mock_task, client, acme_member, route):
    payload = {"USE_MODSECURITY": "yes", "MODSECURITY_CRS_PARANOIA_LEVEL": "3"}
    client.force_login(acme_member)
    res = client.patch(
        "/api/ingress/routes/app.example.com/settings/",
        payload,
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json() == payload
    mock_task.delay.assert_called_once_with("app.example.com", payload)


@pytest.mark.django_db
def test_patch_settings_rejects_unknown_keys(client, acme_member, route):
    client.force_login(acme_member)
    res = client.patch(
        "/api/ingress/routes/app.example.com/settings/",
        {"UNKNOWN_KEY": "yes"},
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "UNKNOWN_KEY" in res.json()["detail"]


@pytest.mark.django_db
def test_patch_settings_rejects_paranoia_level_out_of_range(client, acme_member, route):
    client.force_login(acme_member)
    res = client.patch(
        "/api/ingress/routes/app.example.com/settings/",
        {"MODSECURITY_CRS_PARANOIA_LEVEL": "5"},
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_patch_settings_rejects_paranoia_level_zero(client, acme_member, route):
    client.force_login(acme_member)
    res = client.patch(
        "/api/ingress/routes/app.example.com/settings/",
        {"MODSECURITY_CRS_PARANOIA_LEVEL": "0"},
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_patch_settings_rejects_non_integer_paranoia_level(client, acme_member, route):
    client.force_login(acme_member)
    res = client.patch(
        "/api/ingress/routes/app.example.com/settings/",
        {"MODSECURITY_CRS_PARANOIA_LEVEL": "high"},
        content_type="application/json",
    )
    assert res.status_code == 400
