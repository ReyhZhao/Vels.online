from unittest.mock import patch

import pytest

from ingress.models import Route
from ingress.tasks import check_route_dns
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def route(acme):
    return Route.objects.create(
        fqdn="app.example.com",
        backend_host="10.0.0.1",
        backend_port=8080,
        organization=acme,
        status=Route.STATUS_ACTIVE,
    )


@pytest.mark.django_db
@patch("ingress.tasks.socket.gethostbyname", return_value="203.0.113.42")
def test_dns_match_sets_dns_ok_true(mock_gethostbyname, route, settings):
    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    check_route_dns(route.pk)
    route.refresh_from_db()
    assert route.dns_ok is True
    mock_gethostbyname.assert_called_once_with("app.example.com")


@pytest.mark.django_db
@patch("ingress.tasks.socket.gethostbyname", return_value="1.2.3.4")
def test_dns_mismatch_sets_dns_ok_false(mock_gethostbyname, route, settings):
    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    check_route_dns(route.pk)
    route.refresh_from_db()
    assert route.dns_ok is False


@pytest.mark.django_db
@patch("ingress.tasks.socket.gethostbyname", side_effect=OSError("Name resolution failed"))
def test_dns_resolution_failure_sets_dns_ok_false(mock_gethostbyname, route, settings):
    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    check_route_dns(route.pk)
    route.refresh_from_db()
    assert route.dns_ok is False


@pytest.mark.django_db
def test_task_silently_ignores_missing_route(db):
    check_route_dns(99999)  # should not raise


@pytest.mark.django_db
@patch("ingress.tasks.socket.gethostbyname", return_value="203.0.113.42")
def test_task_enqueued_on_route_create(mock_gethostbyname, client, settings, db, django_user_model):
    from unittest.mock import patch as _patch
    from security.models import Organization, OrganizationMembership

    settings.BUNKERWEB_PUBLIC_IP = "203.0.113.42"
    org = Organization.objects.create(name="Acme", slug="acme2", wazuh_group="acme2")
    user = django_user_model.objects.create_user(username="bob", password="pass")
    OrganizationMembership.objects.create(user=user, organization=org)
    client.force_login(user)

    with _patch("ingress.views.BunkerWebClient") as MockBW, \
         _patch("ingress.views.check_route_dns") as mock_task:
        MockBW.return_value.create_service.return_value = {}
        res = client.post(
            "/api/ingress/routes/?org=acme2",
            {"fqdn": "new.example.com", "backend_host": "10.0.0.1", "backend_port": 8080},
            content_type="application/json",
        )
        assert res.status_code == 201
        route_id = res.json()["id"]
        mock_task.delay.assert_called_once_with(route_id)
