from unittest.mock import patch

import pytest

from ingress.bunkerweb import BunkerWebError
from ingress.models import Route
from ingress.tasks import push_route_settings
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


WAF_PAYLOAD = {"USE_MODSECURITY": "yes", "MODSECURITY_CRS_PARANOIA_LEVEL": "2"}


@pytest.mark.django_db
@patch("ingress.bunkerweb.BunkerWebClient.update_service_settings")
def test_push_settings_success_calls_bunkerweb(mock_update, route):
    push_route_settings("app.example.com", WAF_PAYLOAD)
    mock_update.assert_called_once_with("app.example.com", WAF_PAYLOAD)
    route.refresh_from_db()
    assert route.status == Route.STATUS_ACTIVE


@pytest.mark.django_db
@patch("ingress.bunkerweb.BunkerWebClient.update_service_settings")
def test_push_settings_bunkerweb_error_sets_status_error(mock_update, route):
    mock_update.side_effect = BunkerWebError(500, "error")
    push_route_settings("app.example.com", WAF_PAYLOAD)
    route.refresh_from_db()
    assert route.status == Route.STATUS_ERROR


@pytest.mark.django_db
def test_push_settings_silently_ignores_missing_route(db):
    push_route_settings("missing.example.com", WAF_PAYLOAD)
