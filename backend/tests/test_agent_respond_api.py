"""Integration tests for AgentRespondView and AgentResponseHistoryView."""
from unittest.mock import patch

import pytest

from automations.models import WazuhActiveResponse
from incidents.models import Incident, Task, WazuhResponseExecution
from security.models import Organization
from security.wazuh import WazuhAPIError


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="user", password="pass")


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def wr(db, staff):
    return WazuhActiveResponse.objects.create(
        name="Firewall Drop",
        command="firewall-drop",
        platforms=["linux"],
        default_args="-srcip 1.2.3.4",
        timeout=30,
        available_in_security_overview=True,
        created_by=staff,
    )


@pytest.fixture
def wr_not_in_overview(db, staff):
    return WazuhActiveResponse.objects.create(
        name="Hidden",
        command="hidden-cmd",
        platforms=["linux"],
        available_in_security_overview=False,
        created_by=staff,
    )


_MOCK_AGENTS = [{"id": "001", "name": "server1", "ip": "10.0.0.1", "status": "active", "os": {"platform": "linux"}}]
_MOCK_UBUNTU_AGENTS = [{"id": "001", "name": "server1", "ip": "10.0.0.1", "status": "active", "os": {"platform": "ubuntu"}}]


def _mock_run(return_value=(200, {})):
    return patch("security.wazuh.WazuhClient.run_active_response", return_value=return_value)


def _mock_agents(agents=None):
    return patch("security.wazuh.WazuhClient.get_agents", return_value=agents or _MOCK_AGENTS)


# ── AgentRespondView ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_respond_requires_staff(client, regular_user, wr, org):
    client.force_login(regular_user)
    resp = client.post(
        "/api/security/agents/001/respond/",
        {"org": org.slug, "wazuh_response": wr.id},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_respond_rejects_non_overview_response(client, staff, wr_not_in_overview, org):
    client.force_login(staff)
    with _mock_agents():
        resp = client.post(
            "/api/security/agents/001/respond/",
            {"org": org.slug, "wazuh_response": wr_not_in_overview.id},
            content_type="application/json",
        )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_respond_rejects_wrong_platform(client, staff, org, db, django_user_model):
    wr_win = WazuhActiveResponse.objects.create(
        name="Windows Only",
        command="win-cmd",
        platforms=["windows"],
        available_in_security_overview=True,
        created_by=staff,
    )
    client.force_login(staff)
    with _mock_agents():
        resp = client.post(
            "/api/security/agents/001/respond/",
            {"org": org.slug, "wazuh_response": wr_win.id},
            content_type="application/json",
        )
    assert resp.status_code == 400
    assert "platform" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_respond_allows_ubuntu_agent_on_linux_response(client, staff, wr, org):
    """Ubuntu agents report 'ubuntu' as platform; must match 'linux' responses."""
    client.force_login(staff)
    with _mock_agents(_MOCK_UBUNTU_AGENTS), _mock_run():
        resp = client.post(
            "/api/security/agents/001/respond/",
            {"org": org.slug, "wazuh_response": wr.id},
            content_type="application/json",
        )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_respond_standalone_creates_execution_no_task(client, staff, wr, org):
    client.force_login(staff)
    with _mock_agents(), _mock_run():
        resp = client.post(
            "/api/security/agents/001/respond/",
            {"org": org.slug, "wazuh_response": wr.id},
            content_type="application/json",
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["incident"] is None
    assert data["task_id"] is None
    assert WazuhResponseExecution.objects.filter(agent_ids__icontains='"001"').exists()
    execution = WazuhResponseExecution.objects.get(agent_ids__icontains='"001"')
    assert execution.incident is None
    assert execution.task is None


@pytest.mark.django_db
def test_respond_incident_linked_creates_task_and_event(client, staff, wr, org):
    incident = Incident.objects.create(
        organization=org,
        title="Test",
        display_id="INC-0001",
        severity="high",
    )
    client.force_login(staff)
    with _mock_agents(), _mock_run():
        resp = client.post(
            "/api/security/agents/001/respond/",
            {"org": org.slug, "wazuh_response": wr.id, "incident": "INC-0001"},
            content_type="application/json",
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["incident"] == "INC-0001"
    assert data["task_id"] is not None

    task = Task.objects.get(pk=data["task_id"])
    assert task.task_type == Task.TYPE_WAZUH_RESPONSE
    assert task.state == Task.STATE_DONE

    execution = WazuhResponseExecution.objects.get(task=task)
    assert execution.incident == incident

    from incidents.models import IncidentEvent
    assert IncidentEvent.objects.filter(incident=incident, kind="wazuh_response_dispatched").exists()


# ── AgentResponseHistoryView ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_response_history_lists_executions(client, staff, wr, org):
    WazuhResponseExecution.objects.create(
        wazuh_response=wr,
        executed_by=staff,
        agent_ids=["001"],
        resolved_args="-srcip 1.2.3.4",
        timeout_used=30,
        wazuh_status_code=200,
    )
    client.force_login(staff)
    with _mock_agents():
        resp = client.get(f"/api/security/agents/001/responses/?org={org.slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["executions"]) == 1
    ex = data["executions"][0]
    assert ex["response_name"] == "Firewall Drop"
    assert ex["command"] == "firewall-drop"
    assert ex["wazuh_status_code"] == 200


@pytest.mark.django_db
def test_response_history_empty_for_other_agent(client, staff, wr, org):
    WazuhResponseExecution.objects.create(
        wazuh_response=wr,
        executed_by=staff,
        agent_ids=["002"],
        resolved_args="",
        timeout_used=0,
    )
    client.force_login(staff)
    with _mock_agents():
        resp = client.get(f"/api/security/agents/001/responses/?org={org.slug}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.django_db
def test_response_history_timeout_zero(client, staff, wr, org):
    WazuhResponseExecution.objects.create(
        wazuh_response=wr,
        executed_by=staff,
        agent_ids=["001"],
        resolved_args="",
        timeout_used=0,
    )
    client.force_login(staff)
    with _mock_agents():
        resp = client.get(f"/api/security/agents/001/responses/?org={org.slug}")
    ex = resp.json()["executions"][0]
    assert ex["timeout_used"] == 0
