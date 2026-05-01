from unittest.mock import MagicMock, patch

import pytest

from status.uptimerobot import get_monitors


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


@patch("status.uptimerobot.requests.post")
def test_get_monitors_returns_monitors(mock_post):
    mock_post.return_value = _mock_response({
        "stat": "ok",
        "monitors": [
            {
                "id": 12345,
                "friendly_name": "My Site",
                "status": 2,
                "custom_uptime_ratio": "99.99",
                "average_response_time": "150",
            }
        ],
    })

    monitors = get_monitors()

    assert len(monitors) == 1
    assert monitors[0]["friendly_name"] == "My Site"
    assert monitors[0]["status"] == 2


@patch("status.uptimerobot.requests.post")
def test_get_monitors_passes_api_key(mock_post, monkeypatch):
    monkeypatch.setenv("UPTIMEROBOT_API_KEY", "test-key-123")
    mock_post.return_value = _mock_response({"stat": "ok", "monitors": []})

    get_monitors()

    _, kwargs = mock_post.call_args
    assert kwargs["data"]["api_key"] == "test-key-123"


@patch("status.uptimerobot.requests.post")
def test_get_monitors_requests_7day_uptime(mock_post):
    mock_post.return_value = _mock_response({"stat": "ok", "monitors": []})

    get_monitors()

    _, kwargs = mock_post.call_args
    assert kwargs["data"]["custom_uptime_ratios"] == "7"


@patch("status.uptimerobot.requests.post")
def test_get_monitors_raises_on_api_error(mock_post):
    mock_post.return_value = _mock_response({
        "stat": "fail",
        "error": {"type": "invalid_parameter", "message": "bad key"},
    })

    with pytest.raises(RuntimeError, match="UptimeRobot API error"):
        get_monitors()


@patch("status.uptimerobot.requests.post")
def test_get_monitors_raises_on_http_error(mock_post):
    mock = MagicMock()
    mock.raise_for_status.side_effect = Exception("HTTP 500")
    mock_post.return_value = mock

    with pytest.raises(Exception, match="HTTP 500"):
        get_monitors()


@patch("status.uptimerobot.requests.post")
def test_get_monitors_include_logs_sets_response_times(mock_post):
    mock_post.return_value = _mock_response({"stat": "ok", "monitors": []})

    get_monitors(include_logs=True)

    _, kwargs = mock_post.call_args
    assert kwargs["data"]["response_times"] == 1


@patch("status.uptimerobot.requests.post")
def test_get_monitors_exclude_logs_by_default(mock_post):
    mock_post.return_value = _mock_response({"stat": "ok", "monitors": []})

    get_monitors()

    _, kwargs = mock_post.call_args
    assert kwargs["data"]["response_times"] == 0
