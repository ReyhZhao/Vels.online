from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from ingress.bunkerweb import BunkerWebClient, BunkerWebError

_BASE_URL = "https://bunkerweb.internal"
_TOKEN = "test-token-abc"


@pytest.fixture(autouse=True)
def bunkerweb_settings(settings):
    settings.BUNKERWEB_API_URL = _BASE_URL
    settings.BUNKERWEB_API_TOKEN = _TOKEN


def _ok(payload=None):
    m = MagicMock()
    m.ok = True
    m.json.return_value = payload or {}
    return m


def _error(status_code=500, body="Internal Server Error"):
    m = MagicMock()
    m.ok = False
    m.status_code = status_code
    m.text = body
    return m


# ----------------------------------------------------------------- auth header


@patch("ingress.bunkerweb.requests.post")
def test_auth_header_on_create(mock_post):
    mock_post.return_value = _ok()
    BunkerWebClient().create_service("app.example.com", "10.0.0.1", 8080, "http")
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TOKEN}"


@patch("ingress.bunkerweb.requests.delete")
def test_auth_header_on_delete(mock_delete):
    mock_delete.return_value = _ok()
    BunkerWebClient().delete_service("app.example.com")
    _, kwargs = mock_delete.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TOKEN}"


@patch("ingress.bunkerweb.requests.get")
def test_auth_header_on_get_settings(mock_get):
    mock_get.return_value = _ok({"USE_MODSECURITY": "yes"})
    BunkerWebClient().get_service_settings("app.example.com")
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TOKEN}"


@patch("ingress.bunkerweb.requests.patch")
def test_auth_header_on_update_settings(mock_patch):
    mock_patch.return_value = _ok()
    BunkerWebClient().update_service_settings("app.example.com", {"USE_MODSECURITY": "yes"})
    _, kwargs = mock_patch.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TOKEN}"


# -------------------------------------------------------------- create_service


@patch("ingress.bunkerweb.requests.post")
def test_create_service_success(mock_post):
    mock_post.return_value = _ok({"id": "app.example.com"})
    result = BunkerWebClient().create_service("app.example.com", "10.0.0.1", 8080, "http")
    assert result == {"id": "app.example.com"}
    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert url == f"{_BASE_URL}/services"
    payload = mock_post.call_args[1]["json"]
    assert payload["server_name"] == "app.example.com"
    assert payload["backend_host"] == "10.0.0.1"
    assert payload["backend_port"] == 8080
    assert payload["backend_protocol"] == "http"


@patch("ingress.bunkerweb.requests.post")
def test_create_service_bunkerweb_error(mock_post):
    mock_post.return_value = _error(409, "service already exists")
    with pytest.raises(BunkerWebError) as exc_info:
        BunkerWebClient().create_service("app.example.com", "10.0.0.1", 8080, "http")
    assert exc_info.value.status_code == 409
    assert "service already exists" in exc_info.value.body


# -------------------------------------------------------------- delete_service


@patch("ingress.bunkerweb.requests.delete")
def test_delete_service_success(mock_delete):
    mock_delete.return_value = _ok()
    BunkerWebClient().delete_service("app.example.com")
    url = mock_delete.call_args[0][0]
    assert url == f"{_BASE_URL}/services/app.example.com"


@patch("ingress.bunkerweb.requests.delete")
def test_delete_service_not_found_raises(mock_delete):
    mock_delete.return_value = _error(404, "service not found")
    with pytest.raises(BunkerWebError) as exc_info:
        BunkerWebClient().delete_service("missing.example.com")
    assert exc_info.value.status_code == 404


# --------------------------------------------------------- get_service_settings


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_returns_dict(mock_get):
    payload = {"USE_MODSECURITY": "yes", "MODSECURITY_CRS_PARANOIA_LEVEL": "2"}
    mock_get.return_value = _ok(payload)
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == payload
    url = mock_get.call_args[0][0]
    assert url == f"{_BASE_URL}/services/app.example.com"
    assert mock_get.call_args[1]["params"] == {"full": "true"}


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_unwraps_data_envelope(mock_get):
    inner = {"USE_MODSECURITY": "yes", "MODSECURITY_CRS_PARANOIA_LEVEL": "3"}
    mock_get.return_value = _ok({"status": "success", "data": inner})
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == inner


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_unwraps_settings_envelope(mock_get):
    inner = {"USE_WHITELIST": "no"}
    mock_get.return_value = _ok({"status": "success", "settings": inner})
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == inner


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_unwraps_config_envelope(mock_get):
    """full=true response: envelope key is 'config', values are dicts with a 'value' key."""
    raw_config = {
        "USE_MODSECURITY": {"value": "yes", "global": True, "method": "ui", "default": "yes", "template": None},
        "LIMIT_REQ_RATE": {"value": "100r/s", "global": False, "method": "ui", "default": "50r/s", "template": None},
    }
    mock_get.return_value = _ok({"status": "success", "service": "app.example.com", "config": raw_config})
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == {"USE_MODSECURITY": "yes", "LIMIT_REQ_RATE": "100r/s"}


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_extracts_value_from_nested_entries(mock_get):
    """Even without an envelope key, nested {value: ...} entries are flattened."""
    payload = {
        "USE_WHITELIST": {"value": "no", "global": True, "method": "default", "default": "no", "template": None},
    }
    mock_get.return_value = _ok(payload)
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == {"USE_WHITELIST": "no"}


@patch("ingress.bunkerweb.requests.get")
def test_get_service_settings_non_dict_returns_empty(mock_get):
    mock_get.return_value = _ok([])
    result = BunkerWebClient().get_service_settings("app.example.com")
    assert result == {}


# ------------------------------------------------------ update_service_settings


@patch("ingress.bunkerweb.requests.patch")
def test_update_service_settings_sends_payload(mock_patch):
    new_settings = {"USE_MODSECURITY": "no", "USE_LIMIT_REQ": "yes"}
    mock_patch.return_value = _ok(new_settings)
    result = BunkerWebClient().update_service_settings("app.example.com", new_settings)
    assert result == new_settings
    url = mock_patch.call_args[0][0]
    assert url == f"{_BASE_URL}/services/app.example.com"
    assert mock_patch.call_args[1]["json"] == new_settings


# ------------------------------------------------------------- list_services


@patch("ingress.bunkerweb.requests.get")
def test_list_services_returns_list(mock_get):
    envelope = {
        "status": "success",
        "services": [
            {"id": "a.example.com", "method": "ui", "is_draft": False},
            {"id": "b.example.com", "method": "ui", "is_draft": False},
        ],
    }
    mock_get.return_value = _ok(envelope)
    result = BunkerWebClient().list_services()
    assert len(result) == 2
    assert result[0]["server_name"] == "a.example.com"
    assert result[1]["server_name"] == "b.example.com"
    url = mock_get.call_args[0][0]
    assert url == f"{_BASE_URL}/services"


@patch("ingress.bunkerweb.requests.get")
def test_list_services_unwraps_envelope(mock_get):
    envelope = {
        "status": "success",
        "services": [{"id": "svc.example.com", "method": "ui", "is_draft": False}],
    }
    mock_get.return_value = _ok(envelope)
    result = BunkerWebClient().list_services()
    assert isinstance(result, list)
    assert result[0]["server_name"] == "svc.example.com"
    assert "id" not in result[0]


@patch("ingress.bunkerweb.requests.get")
def test_list_services_auth_header(mock_get):
    mock_get.return_value = _ok({"status": "success", "services": []})
    BunkerWebClient().list_services()
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TOKEN}"


@patch("ingress.bunkerweb.requests.get")
def test_list_services_bunkerweb_error(mock_get):
    mock_get.return_value = _error(500, "server error")
    with pytest.raises(BunkerWebError) as exc_info:
        BunkerWebClient().list_services()
    assert exc_info.value.status_code == 500


# -------------------------------------------------- network error → BunkerWebError


@patch("ingress.bunkerweb.requests.get")
def test_network_error_raises_bunkerweb_error(mock_get):
    mock_get.side_effect = RequestsConnectionError("Connection refused")
    with pytest.raises(BunkerWebError) as exc_info:
        BunkerWebClient().list_services()
    assert exc_info.value.status_code == 0
    assert "Connection refused" in exc_info.value.body


@patch("ingress.bunkerweb.requests.post")
def test_network_error_on_create_raises_bunkerweb_error(mock_post):
    mock_post.side_effect = RequestsConnectionError("timeout")
    with pytest.raises(BunkerWebError) as exc_info:
        BunkerWebClient().create_service("app.example.com", "10.0.0.1", 8080, "http")
    assert exc_info.value.status_code == 0
