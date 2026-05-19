from unittest.mock import patch

import pytest

from ingress.models import Route
from security.models import Organization, OrganizationMembership
from security.opensearch import OpenSearchError

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
def route(acme):
    return Route.objects.create(
        fqdn="app.example.com",
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )


_OS_RESULT = {
    "logs": [{"_id": "abc", "data": {"srcip": "1.2.3.4"}}],
    "total": 1,
    "summary": {"total": 1, "blocked": 0},
}

# ── GET /api/ingress/routes/<fqdn>/logs/ ────────────────────────────────────


@pytest.mark.django_db
def test_logs_requires_auth(client, route):
    assert client.get("/api/ingress/routes/app.example.com/logs/").status_code == 401


@pytest.mark.django_db
def test_logs_non_member_forbidden(client, alice, route):
    client.force_login(alice)
    assert client.get("/api/ingress/routes/app.example.com/logs/").status_code == 403


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_returns_accesslog_by_default(MockOS, client, acme_member, route):
    MockOS.return_value.get_route_logs.return_value = _OS_RESULT
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/logs/")
    assert res.status_code == 200
    data = res.json()
    assert data["logs"] == _OS_RESULT["logs"]
    assert data["total"] == 1
    assert data["summary"] == {"total": 1, "blocked": 0}
    MockOS.return_value.get_route_logs.assert_called_once_with(
        fqdn="app.example.com",
        log_type="accesslog",
        hours=24,
        offset=0,
        limit=50,
        srcip=None,
    )


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_modsecurity_type_forwarded(MockOS, client, acme_member, route):
    result = {"logs": [], "total": 0, "summary": {"total": 0, "blocked": 0}}
    MockOS.return_value.get_route_logs.return_value = result
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/logs/?type=modsecurity")
    assert res.status_code == 200
    MockOS.return_value.get_route_logs.assert_called_once_with(
        fqdn="app.example.com",
        log_type="modsecurity",
        hours=24,
        offset=0,
        limit=50,
        srcip=None,
    )


@pytest.mark.django_db
def test_logs_invalid_type_returns_400(client, acme_member, route):
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/logs/?type=nginx")
    assert res.status_code == 400


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_srcip_filter_forwarded(MockOS, client, acme_member, route):
    MockOS.return_value.get_route_logs.return_value = _OS_RESULT
    client.force_login(acme_member)
    client.get("/api/ingress/routes/app.example.com/logs/?srcip=1.2.3.4")
    _, kwargs = MockOS.return_value.get_route_logs.call_args
    assert kwargs["srcip"] == "1.2.3.4"


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_hours_offset_limit_forwarded(MockOS, client, acme_member, route):
    MockOS.return_value.get_route_logs.return_value = _OS_RESULT
    client.force_login(acme_member)
    client.get("/api/ingress/routes/app.example.com/logs/?hours=168&offset=50&limit=100")
    _, kwargs = MockOS.return_value.get_route_logs.call_args
    assert kwargs["hours"] == 168
    assert kwargs["offset"] == 50
    assert kwargs["limit"] == 100


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_limit_capped_at_200(MockOS, client, acme_member, route):
    MockOS.return_value.get_route_logs.return_value = _OS_RESULT
    client.force_login(acme_member)
    client.get("/api/ingress/routes/app.example.com/logs/?limit=9999")
    _, kwargs = MockOS.return_value.get_route_logs.call_args
    assert kwargs["limit"] == 200


@pytest.mark.django_db
def test_logs_invalid_hours_returns_400(client, acme_member, route):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/app.example.com/logs/?hours=bad").status_code == 400


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_opensearch_error_returns_empty(MockOS, client, acme_member, route):
    MockOS.return_value.get_route_logs.side_effect = OpenSearchError("down")
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/logs/")
    assert res.status_code == 200
    data = res.json()
    assert data["logs"] == []
    assert data["total"] == 0
    assert data["summary"] == {"total": 0, "blocked": 0}


@pytest.mark.django_db
@patch("ingress.views.OpenSearchClient")
def test_logs_staff_bypass(MockOS, client, route, django_user_model):
    staff = django_user_model.objects.create_user(username="s", password="p", is_staff=True)
    MockOS.return_value.get_route_logs.return_value = _OS_RESULT
    client.force_login(staff)
    assert client.get("/api/ingress/routes/app.example.com/logs/").status_code == 200


@pytest.mark.django_db
def test_logs_route_not_found(client, acme_member):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/missing.example.com/logs/").status_code == 404
