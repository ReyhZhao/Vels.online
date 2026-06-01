"""Unit tests for WazuhClient.run_active_response and automations.interpolation."""
from unittest.mock import MagicMock, patch

import pytest

from automations.interpolation import interpolate_args
from automations.models import WazuhActiveResponse
from incidents.models import Asset, IOC, Incident, Task, WazuhResponseExecution
from security.models import Organization
from security.wazuh import WazuhAPIError, WazuhClient


# ── WazuhClient.run_active_response ──────────────────────────────────────────


@pytest.fixture
def wazuh_client():
    client = WazuhClient()
    client._base_url = "https://wazuh.example.com"
    client._user = "admin"
    client._password = "secret"
    return client


def _mock_put_response(status_code=200, error_code=0):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"error": error_code, "data": {"affected_items": []}}
    resp.raise_for_status.return_value = None
    return resp


def test_run_active_response_builds_correct_payload(wazuh_client):
    with patch("security.wazuh.requests.put") as mock_put:
        mock_put.return_value = _mock_put_response()
        with patch.object(wazuh_client, "_get_token", return_value="tok"):
            wazuh_client.run_active_response("firewall-drop", ["001", "002"], args="-srcip 1.2.3.4", timeout=30)

    call_kwargs = mock_put.call_args[1]
    body = call_kwargs["json"]
    assert body["command"] == "firewall-drop"
    assert "-srcip" in body["arguments"]
    assert "1.2.3.4" in body["arguments"]
    assert set(body["agents_list"]) == {"001", "002"}
    assert body["timeout"] == 30


def test_run_active_response_no_timeout_omits_timeout_field(wazuh_client):
    with patch("security.wazuh.requests.put") as mock_put:
        mock_put.return_value = _mock_put_response()
        with patch.object(wazuh_client, "_get_token", return_value="tok"):
            wazuh_client.run_active_response("firewall-drop", ["001"])

    body = mock_put.call_args[1]["json"]
    assert "timeout" not in body


def test_run_active_response_raises_on_http_error(wazuh_client):
    import requests as req_lib

    resp = MagicMock()
    resp.status_code = 403
    resp.raise_for_status.side_effect = req_lib.exceptions.HTTPError("403 Forbidden")

    with patch("security.wazuh.requests.put", return_value=resp):
        with patch.object(wazuh_client, "_get_token", return_value="tok"):
            with pytest.raises(WazuhAPIError):
                wazuh_client.run_active_response("cmd", ["001"])


def test_run_active_response_returns_status_code_and_body(wazuh_client):
    with patch("security.wazuh.requests.put") as mock_put:
        mock_put.return_value = _mock_put_response(status_code=200)
        with patch.object(wazuh_client, "_get_token", return_value="tok"):
            code, body = wazuh_client.run_active_response("cmd", ["001"])

    assert code == 200
    assert "data" in body


# ── Variable interpolation ────────────────────────────────────────────────────


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(db, org):
    return Incident.objects.create(
        organization=org,
        title="Test",
        display_id="INC-0001",
        severity="high",
    )


@pytest.mark.django_db
def test_interpolate_incident_id(incident):
    result = interpolate_args("id={{incident.id}}", incident)
    assert result == f"id={incident.id}"


@pytest.mark.django_db
def test_interpolate_incident_display_id(incident):
    result = interpolate_args("{{incident.display_id}}", incident)
    assert result == "INC-0001"


@pytest.mark.django_db
def test_interpolate_asset_ip(incident, org):
    asset = Asset.objects.create(organization=org, kind="host", name="server1", ip_address="10.0.0.1")
    incident.assets.add(asset)
    result = interpolate_args("-srcip {{asset.ip}}", incident)
    assert result == "-srcip 10.0.0.1"


@pytest.mark.django_db
def test_interpolate_ioc_ip(incident):
    IOC.objects.create(incident=incident, kind="ip", value="192.168.1.50")
    result = interpolate_args("{{ioc.ip}}", incident)
    assert result == "192.168.1.50"


@pytest.mark.django_db
def test_interpolate_ioc_domain(incident):
    IOC.objects.create(incident=incident, kind="domain", value="evil.example.com")
    result = interpolate_args("block {{ioc.domain}}", incident)
    assert result == "block evil.example.com"


@pytest.mark.django_db
def test_interpolate_missing_ioc_leaves_placeholder(incident):
    result = interpolate_args("block {{ioc.ip}}", incident)
    assert result == "block {{ioc.ip}}"


@pytest.mark.django_db
def test_interpolate_unknown_placeholder_unchanged(incident):
    result = interpolate_args("{{unknown.field}}", incident)
    assert result == "{{unknown.field}}"


@pytest.mark.django_db
def test_interpolate_empty_string(incident):
    result = interpolate_args("", incident)
    assert result == ""


@pytest.mark.django_db
def test_interpolate_partial_resolution(incident, org):
    asset = Asset.objects.create(organization=org, kind="host", name="s1", ip_address="10.10.0.1")
    incident.assets.add(asset)
    result = interpolate_args("ip={{asset.ip}} domain={{ioc.domain}}", incident)
    assert result == "ip=10.10.0.1 domain={{ioc.domain}}"


# ── WazuhResponseExecution creation via task run ──────────────────────────────


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def wazuh_response_catalog(db, staff):
    return WazuhActiveResponse.objects.create(
        name="Firewall Drop",
        command="firewall-drop",
        platforms=["linux"],
        default_args="-srcip {{asset.ip}}",
        timeout=60,
        created_by=staff,
    )


@pytest.fixture
def wazuh_task(db, incident, wazuh_response_catalog):
    return Task.objects.create(
        incident=incident,
        title="Block attacker",
        task_type=Task.TYPE_WAZUH_RESPONSE,
        wazuh_response=wazuh_response_catalog,
    )


@pytest.mark.django_db
def test_wazuh_task_run_creates_execution(client, staff, wazuh_task, incident, org):
    asset = Asset.objects.create(organization=org, kind="host", name="s1", agent_name="wazuh-001", ip_address="10.0.0.1")
    incident.assets.add(asset)

    with patch("security.wazuh.WazuhClient.run_active_response", return_value=(200, {"error": 0})):
        with patch("security.wazuh.WazuhClient._get_token", return_value="tok"):
            client.force_login(staff)
            resp = client.post(f"/api/tasks/{wazuh_task.pk}/run/", content_type="application/json")

    assert resp.status_code == 200
    assert WazuhResponseExecution.objects.filter(task=wazuh_task).exists()
    execution = WazuhResponseExecution.objects.get(task=wazuh_task)
    assert execution.wazuh_status_code == 200


@pytest.mark.django_db
def test_wazuh_task_run_sets_state_done_on_error(client, staff, wazuh_task):
    with patch("security.wazuh.WazuhClient.run_active_response", side_effect=WazuhAPIError("fail")):
        with patch("security.wazuh.WazuhClient._get_token", return_value="tok"):
            client.force_login(staff)
            resp = client.post(f"/api/tasks/{wazuh_task.pk}/run/", content_type="application/json")

    assert resp.status_code == 200
    wazuh_task.refresh_from_db()
    assert wazuh_task.state == Task.STATE_DONE
    assert wazuh_task.automation_error is not None
    assert WazuhResponseExecution.objects.filter(task=wazuh_task).exists()
