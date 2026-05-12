from unittest.mock import patch

import pytest
import requests
from django.core.cache import cache
from django.test import Client

from status.models import MonitorVisibility


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()

_RAW_MONITOR = {
    "id": 12345,
    "friendly_name": "My Site",
    "status": 2,
    "custom_uptime_ratio": "99.95",
    "average_response_time": "120",
    "logs": [
        {"type": 1, "datetime": 1617800000, "duration": 300},
        {"type": 2, "datetime": 1617800300, "duration": 0},
    ],
}


@pytest.fixture
def visible_monitor():
    return MonitorVisibility.objects.create(
        monitor_id="12345", name="My Site", is_visible=True
    )


@pytest.fixture
def hidden_monitor():
    return MonitorVisibility.objects.create(
        monitor_id="99999", name="Internal", is_visible=False
    )


# --- GET /api/status/ ---

@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_status_returns_visible_monitors(mock_get, client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    response = client.get("/api/status/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Site"
    assert data[0]["status"] == "up"
    assert "logs" not in data[0]


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_status_excludes_hidden_monitors(mock_get, client, hidden_monitor):
    raw = {**_RAW_MONITOR, "id": 99999}
    mock_get.return_value = [raw]
    response = client.get("/api/status/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_status_uses_cache_on_second_request(mock_get, client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    client.get("/api/status/")
    client.get("/api/status/")
    assert mock_get.call_count == 1


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_admin_status_includes_logs(mock_get, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    response = admin_client.get("/api/status/")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data[0]
    assert data[0]["logs"][0]["type"] == "down"
    assert data[0]["logs"][1]["type"] == "up"
    assert data[0]["logs"][0]["duration_seconds"] == 300


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_admin_status_bypasses_cache(mock_get, client, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    client.get("/api/status/")        # warms cache
    admin_client.get("/api/status/")  # should bypass cache and fetch again
    assert mock_get.call_count == 2


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_admin_status_requests_logs_from_uptimerobot(mock_get, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    admin_client.get("/api/status/")
    mock_get.assert_called_once_with(include_logs=True)


# --- POST /api/status/refresh/ ---

@pytest.mark.django_db
def test_me_sets_csrf_cookie(django_user_model):
    """GET /api/me/ must write the csrftoken cookie so the SPA can attach
    X-CSRFToken on POST/PATCH requests. All other API views are csrf_exempt,
    so without this call the cookie is never set for SPA-only users."""
    user = django_user_model.objects.create_user(username="admin_csrf", password="pass", is_staff=True)
    c = Client()
    c.force_login(user)
    res = c.get("/api/me/")
    assert "csrftoken" in res.cookies


@pytest.mark.django_db
def test_refresh_returns_401_for_anonymous(client):
    response = client.post("/api/status/refresh/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_returns_403_for_non_staff(client, django_user_model):
    user = django_user_model.objects.create_user(username="regular", password="pass")
    client.force_login(user)
    response = client.post("/api/status/refresh/")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_refresh_returns_fresh_data_with_logs(mock_get, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    response = admin_client.post("/api/status/refresh/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "logs" in data[0]
    assert data[0]["logs"][0]["type"] == "down"


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_refresh_updates_public_cache(mock_get, client, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    admin_client.post("/api/status/refresh/")  # warms cache via force refresh
    client.get("/api/status/")                  # should hit cache, not call get_monitors again
    assert mock_get.call_count == 1


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_refresh_public_cache_does_not_include_logs(mock_get, client, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    admin_client.post("/api/status/refresh/")
    response = client.get("/api/status/")
    assert "logs" not in response.json()[0]


# --- MonitorListView: GET /api/status/monitors/ ---


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_monitor_list_no_db_record_defaults_to_hidden(mock_get, admin_client):
    mock_get.return_value = [_RAW_MONITOR]
    # No MonitorVisibility record created — monitor should be returned as hidden
    response = admin_client.get("/api/status/monitors/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["monitor_id"] == "12345"
    assert data[0]["is_visible"] is False


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_monitor_list_explicit_visible_record_preserved(mock_get, admin_client, visible_monitor):
    mock_get.return_value = [_RAW_MONITOR]
    response = admin_client.get("/api/status/monitors/")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["is_visible"] is True


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_monitor_list_explicit_hidden_record_preserved(mock_get, admin_client, hidden_monitor):
    raw = {**_RAW_MONITOR, "id": 99999}
    mock_get.return_value = [raw]
    response = admin_client.get("/api/status/monitors/")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["is_visible"] is False


@pytest.mark.django_db
@patch("status.views.get_monitors")
def test_monitor_list_requires_staff(mock_get, client, django_user_model):
    mock_get.return_value = [_RAW_MONITOR]
    user = django_user_model.objects.create_user(username="regular", password="pass")
    client.force_login(user)
    response = client.get("/api/status/monitors/")
    assert response.status_code == 403


# --- Timeout / connectivity error handling ---

@pytest.mark.django_db
@patch("status.uptimerobot.requests.post")
def test_status_returns_503_on_read_timeout(mock_post, client):
    mock_post.side_effect = requests.exceptions.ReadTimeout()
    response = client.get("/api/status/")
    assert response.status_code == 503
    assert response.json() == {"error": "upstream_unavailable"}


@pytest.mark.django_db
@patch("status.uptimerobot.requests.post")
def test_status_returns_503_on_connection_error(mock_post, client):
    mock_post.side_effect = requests.exceptions.ConnectionError()
    response = client.get("/api/status/")
    assert response.status_code == 503
    assert response.json() == {"error": "upstream_unavailable"}
