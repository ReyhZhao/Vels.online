from unittest.mock import MagicMock, call, patch

import pytest
import requests

from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

_FAKE_TOKEN = "eyJhbGciOiJFUzUxMiJ9.fake-token"
_BASE_URL = "https://wazuh.test:55000"


@pytest.fixture(autouse=True)
def wazuh_env(monkeypatch):
    monkeypatch.setenv("WAZUH_API_URL", _BASE_URL)
    monkeypatch.setenv("WAZUH_API_USER", "wazuh-ro")
    monkeypatch.setenv("WAZUH_API_PASSWORD", "secret")


def _token_response():
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"data": {"token": _FAKE_TOKEN}, "error": 0}
    return m


def _api_response(items, total=None):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {
        "data": {
            "affected_items": items,
            "total_affected_items": total if total is not None else len(items),
        },
        "error": 0,
    }
    return m


def _error_response(message="something went wrong"):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {"error": 1, "message": message}
    return m


# ------------------------------------------------------------------ token / cache


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_token_fetched_and_cached_on_first_call(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = None
    mock_post.return_value = _token_response()
    mock_get.return_value = _api_response([])

    WazuhClient().get_agents("acme")

    mock_post.assert_called_once_with(
        f"{_BASE_URL}/security/user/authenticate",
        auth=("wazuh-ro", "secret"),
        verify=False,
        timeout=10,
    )
    mock_cache.set.assert_called_once_with("wazuh_jwt_token", _FAKE_TOKEN, 800)


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_cached_token_reused_without_re_fetching(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([])

    client = WazuhClient()
    client.get_agents("acme")
    client.get_agents("acme")

    mock_post.assert_not_called()
    assert mock_get.call_count == 2


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_expired_token_triggers_refetch(mock_post, mock_get, mock_cache):
    # Simulate cache miss (token expired / evicted)
    mock_cache.get.return_value = None
    mock_post.return_value = _token_response()
    mock_get.return_value = _api_response([])

    client = WazuhClient()
    client.get_agents("acme")

    assert mock_post.call_count == 1
    assert mock_cache.set.call_count == 1


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.post")
def test_auth_failure_raises_wazuh_auth_error(mock_post, mock_cache):
    mock_cache.get.return_value = None
    mock_post.return_value = _error_response("Invalid credentials")

    with pytest.raises(WazuhAuthError, match="Invalid credentials"):
        WazuhClient().get_agents("acme")


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.post")
def test_auth_http_401_raises_wazuh_auth_error(mock_post, mock_cache):
    """HTTP 401 from raise_for_status() must be translated to WazuhAuthError, not leak as HTTPError."""
    mock_cache.get.return_value = None
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Client Error: Unauthorized")
    mock_post.return_value = resp

    with pytest.raises(WazuhAuthError, match="401"):
        WazuhClient().get_agents("acme")


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_api_http_error_raises_wazuh_api_error(mock_post, mock_get, mock_cache):
    """HTTP errors from _get() must be translated to WazuhAPIError."""
    mock_cache.get.return_value = _FAKE_TOKEN
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error: Not Found")
    mock_get.return_value = resp

    with pytest.raises(WazuhAPIError, match="404"):
        WazuhClient().get_agents("acme")


# ---------------------------------------------------------------- get_agents


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agents_returns_shaped_data(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    agents = [
        {
            "id": "001",
            "name": "server01",
            "ip": "10.0.0.1",
            "status": "active",
            "os": {"name": "Ubuntu", "version": "22.04", "platform": "ubuntu"},
            "lastKeepAlive": "2024-01-15T10:30:00Z",
        }
    ]
    mock_get.return_value = _api_response(agents)

    result = WazuhClient().get_agents("acme")

    assert result == agents
    assert result[0]["name"] == "server01"
    assert result[0]["status"] == "active"


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agents_sends_correct_params(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([])

    WazuhClient().get_agents("acme-corp")

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["groups_list"] == "acme-corp"
    assert "id,name" in kwargs["params"]["select"]


# ------------------------------------------------------------- get_agent_events


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agent_events_respects_offset_and_limit(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([], total=250)

    WazuhClient().get_agent_events("001", hours=24, offset=100, limit=50)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["offset"] == 100
    assert kwargs["params"]["limit"] == 50
    assert kwargs["params"]["agent_ids"] == "001"


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agent_events_returns_events_and_total(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    events = [{"timestamp": "2024-01-15T10:00:00Z", "rule": {"description": "SSH login", "level": 3}}]
    mock_get.return_value = _api_response(events, total=150)

    result = WazuhClient().get_agent_events("001")

    assert result["events"] == events
    assert result["total"] == 150


# --------------------------------------------------------- get_agent_vulnerabilities


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agent_vulnerabilities_respects_offset_and_limit(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([], total=80)

    WazuhClient().get_agent_vulnerabilities("001", offset=50, limit=25)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["offset"] == 50
    assert kwargs["params"]["limit"] == 25


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agent_vulnerabilities_returns_vulns_and_total(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    vulns = [{"cve": "CVE-2024-1234", "severity": "High", "name": "openssl", "version": "1.1.1"}]
    mock_get.return_value = _api_response(vulns, total=45)

    result = WazuhClient().get_agent_vulnerabilities("001")

    assert result["vulnerabilities"] == vulns
    assert result["total"] == 45


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_agent_vulnerabilities_calls_correct_endpoint(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([])

    WazuhClient().get_agent_vulnerabilities("042")

    url = mock_get.call_args[0][0]
    assert url == f"{_BASE_URL}/vulnerability/042"


# ------------------------------------------------- get_vulnerabilities_summary


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_vulnerabilities_summary_sums_per_severity(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    # Each call returns total=1 for whichever severity was requested
    mock_get.return_value = _api_response([], total=1)

    agents = [{"id": "001", "status": "active"}]
    result = WazuhClient().get_vulnerabilities_summary(agents)

    assert result == {"critical": 1, "high": 1, "medium": 1, "low": 1}
    assert mock_get.call_count == 4  # one request per severity


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_vulnerabilities_summary_skips_inactive_agents(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN

    agents = [{"id": "001", "status": "disconnected"}, {"id": "002", "status": "active"}]
    mock_get.return_value = _api_response([], total=3)

    result = WazuhClient().get_vulnerabilities_summary(agents)

    # Only agent 002 (active) queried — 4 requests total
    assert mock_get.call_count == 4
    assert result == {"critical": 3, "high": 3, "medium": 3, "low": 3}


# ----------------------------------------------------- get_events_count


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_get_events_count_sums_active_agents(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    mock_get.return_value = _api_response([], total=10)

    agents = [
        {"id": "001", "status": "active"},
        {"id": "002", "status": "active"},
        {"id": "003", "status": "disconnected"},
    ]
    result = WazuhClient().get_events_count(agents)

    assert result == 20  # 10 per active agent, inactive skipped
    assert mock_get.call_count == 2


# ---------------------------------------------------------------- create_group


@patch("security.wazuh.cache")
@patch("security.wazuh.requests.get")
@patch("security.wazuh.requests.post")
def test_create_group_posts_to_correct_endpoint(mock_post, mock_get, mock_cache):
    mock_cache.get.return_value = _FAKE_TOKEN
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    ok.json.return_value = {"error": 0, "data": {"affected_items": ["new-org"]}}
    # First post is the group creation (token already cached), not auth
    mock_post.return_value = ok

    WazuhClient().create_group("new-org")

    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert url == f"{_BASE_URL}/groups"
    assert mock_post.call_args[1]["json"] == {"group_id": "new-org"}
