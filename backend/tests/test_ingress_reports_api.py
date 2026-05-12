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
def route(acme):
    return Route.objects.create(
        fqdn="app.example.com",
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )


REPORT_ENTRIES = [
    {"timestamp": "2026-05-01T10:00:00Z", "ip": "1.2.3.4", "rule": "sqli", "action": "blocked"},
    {"timestamp": "2026-05-01T11:00:00Z", "ip": "5.6.7.8", "rule": "xss", "action": "blocked"},
]

# ── GET /api/ingress/routes/<fqdn>/reports/ ──────────────────────────────────


@pytest.mark.django_db
def test_reports_requires_auth(client, route):
    assert client.get("/api/ingress/routes/app.example.com/reports/").status_code == 401


@pytest.mark.django_db
def test_reports_non_member_forbidden(client, alice, route):
    client.force_login(alice)
    assert client.get("/api/ingress/routes/app.example.com/reports/").status_code == 403


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_reports_returns_entries_from_bunkerweb(MockBW, client, acme_member, route):
    MockBW.return_value.get_service_reports.return_value = REPORT_ENTRIES
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/reports/")
    assert res.status_code == 200
    data = res.json()
    assert data["entries"] == REPORT_ENTRIES
    MockBW.return_value.get_service_reports.assert_called_once_with("app.example.com")


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_reports_bunkerweb_dict_response_normalised(MockBW, client, acme_member, route):
    MockBW.return_value.get_service_reports.return_value = {"entries": REPORT_ENTRIES, "total": 2}
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/reports/")
    assert res.status_code == 200
    assert res.json()["entries"] == REPORT_ENTRIES


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_reports_bunkerweb_unavailable_returns_empty_not_500(MockBW, client, acme_member, route):
    MockBW.return_value.get_service_reports.side_effect = BunkerWebError(503, "unavailable")
    client.force_login(acme_member)
    res = client.get("/api/ingress/routes/app.example.com/reports/")
    assert res.status_code == 200
    data = res.json()
    assert data["entries"] == []
    assert "message" in data
    assert "unavailable" in data["message"].lower()


@pytest.mark.django_db
@patch("ingress.views.BunkerWebClient")
def test_reports_staff_bypass(MockBW, client, route, django_user_model):
    staff = django_user_model.objects.create_user(username="s", password="p", is_staff=True)
    MockBW.return_value.get_service_reports.return_value = []
    client.force_login(staff)
    assert client.get("/api/ingress/routes/app.example.com/reports/").status_code == 200


@pytest.mark.django_db
def test_reports_route_not_found(client, acme_member):
    client.force_login(acme_member)
    assert client.get("/api/ingress/routes/missing.example.com/reports/").status_code == 404
