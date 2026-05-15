from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from signups.authentik import AuthentikClient, AuthentikAPIError


@pytest.fixture(autouse=True)
def authentik_settings(settings):
    settings.AUTHENTIK_API_URL = "https://auth.example.com"
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
        with pytest.raises(AuthentikAPIError) as exc_info:
            AuthentikClient().create_group("customer:acme")
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_create_invitation_returns_pk_and_token():
    resp = _make_response(201, {"pk": "inv-uuid-xyz", "name": "signup-42"})
    expires = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with patch("signups.authentik.requests.post", return_value=resp):
        result = AuthentikClient().create_invitation("enrollment", expires, name="signup-42")
    assert result["pk"] == "inv-uuid-xyz"
    assert result["token"] == "inv-uuid-xyz"


@pytest.mark.django_db
def test_create_invitation_sends_name_field():
    resp = _make_response(201, {"pk": "inv-uuid-xyz", "name": "signup-42"})
    expires = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with patch("signups.authentik.requests.post", return_value=resp) as mock_post:
        AuthentikClient().create_invitation("enrollment", expires, name="signup-42")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["name"] == "signup-42"


@pytest.mark.django_db
def test_create_invitation_raises_on_error():
    resp = _make_response(500, text="Server error")
    expires = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with patch("signups.authentik.requests.post", return_value=resp):
        with pytest.raises(AuthentikAPIError) as exc_info:
            AuthentikClient().create_invitation("enrollment", expires, name="signup-1")
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
        with pytest.raises(AuthentikAPIError) as exc_info:
            AuthentikClient().create_group("customer:acme")
    assert exc_info.value.status_code == 0


@pytest.mark.django_db
def test_get_flow_uuid_returns_pk():
    resp = _make_response(200, {"results": [{"pk": "flow-uuid-abc", "slug": "main-page-enrollment"}]})
    with patch("signups.authentik.requests.get", return_value=resp):
        uuid = AuthentikClient().get_flow_uuid("main-page-enrollment")
    assert uuid == "flow-uuid-abc"


@pytest.mark.django_db
def test_get_flow_uuid_calls_correct_endpoint():
    resp = _make_response(200, {"results": [{"pk": "flow-uuid-abc"}]})
    with patch("signups.authentik.requests.get", return_value=resp) as mock_get:
        AuthentikClient().get_flow_uuid("main-page-enrollment")
    url = mock_get.call_args.args[0]
    params = mock_get.call_args.kwargs.get("params", {})
    assert "/flows/instances/" in url
    assert params == {"slug": "main-page-enrollment"}


@pytest.mark.django_db
def test_get_flow_uuid_raises_when_no_results():
    resp = _make_response(200, {"results": []})
    with patch("signups.authentik.requests.get", return_value=resp):
        with pytest.raises(AuthentikAPIError) as exc_info:
            AuthentikClient().get_flow_uuid("nonexistent-slug")
    assert exc_info.value.status_code == 0
    assert "nonexistent-slug" in str(exc_info.value)


@pytest.mark.django_db
def test_get_flow_uuid_raises_on_api_error():
    resp = _make_response(403, text="Forbidden")
    with patch("signups.authentik.requests.get", return_value=resp):
        with pytest.raises(AuthentikAPIError) as exc_info:
            AuthentikClient().get_flow_uuid("main-page-enrollment")
    assert exc_info.value.status_code == 403
