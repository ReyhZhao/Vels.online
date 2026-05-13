from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from signups.authentik import AuthentikClient, AuthentikError


@pytest.fixture(autouse=True)
def authentik_settings(settings):
    settings.AUTHENTIK_SERVER_URL = "https://auth.example.com"
    settings.AUTHENTIK_API_TOKEN = "test-token"


def _make_response(status_code, json_data=None, text=""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = status_code < 400
    mock.json.return_value = json_data or {}
    mock.text = text
    return mock


@pytest.mark.django_db
def test_create_group_returns_pk():
    resp = _make_response(201, {"pk": "group-uuid-abc", "name": "customer:acme"})
    with patch("signups.authentik.requests.post", return_value=resp):
        pk = AuthentikClient().create_group("customer:acme")
    assert pk == "group-uuid-abc"


@pytest.mark.django_db
def test_create_group_raises_on_error():
    resp = _make_response(400, text="Bad request")
    with patch("signups.authentik.requests.post", return_value=resp):
        with pytest.raises(AuthentikError) as exc_info:
            AuthentikClient().create_group("customer:acme")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_create_invitation_returns_pk_and_token():
    resp = _make_response(201, {"pk": "inv-uuid-xyz", "name": "invite-slug"})
    expires = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with patch("signups.authentik.requests.post", return_value=resp):
        result = AuthentikClient().create_invitation("enrollment", expires)
    assert result["pk"] == "inv-uuid-xyz"
    assert result["token"] == "inv-uuid-xyz"


@pytest.mark.django_db
def test_create_invitation_raises_on_error():
    resp = _make_response(500, text="Server error")
    expires = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with patch("signups.authentik.requests.post", return_value=resp):
        with pytest.raises(AuthentikError) as exc_info:
            AuthentikClient().create_invitation("enrollment", expires)
    assert exc_info.value.status_code == 500


@pytest.mark.django_db
def test_delete_group_succeeds():
    resp = _make_response(204)
    with patch("signups.authentik.requests.delete", return_value=resp):
        AuthentikClient().delete_group("group-uuid-abc")  # should not raise


@pytest.mark.django_db
def test_delete_group_404_is_silent():
    resp = _make_response(404)
    with patch("signups.authentik.requests.delete", return_value=resp):
        AuthentikClient().delete_group("nonexistent")  # should not raise


@pytest.mark.django_db
def test_delete_invitation_404_is_silent():
    resp = _make_response(404)
    with patch("signups.authentik.requests.delete", return_value=resp):
        AuthentikClient().delete_invitation("nonexistent")  # should not raise


@pytest.mark.django_db
def test_build_invite_url_format():
    url = AuthentikClient().build_invite_url("my-enrollment-flow", "abc-token-123")
    assert url == "https://auth.example.com/if/flow/my-enrollment-flow/?itoken=abc-token-123"


@pytest.mark.django_db
def test_network_error_raises_authentik_error():
    from requests.exceptions import ConnectionError

    with patch("signups.authentik.requests.post", side_effect=ConnectionError("timeout")):
        with pytest.raises(AuthentikError) as exc_info:
            AuthentikClient().create_group("customer:acme")
    assert exc_info.value.status_code == 0
