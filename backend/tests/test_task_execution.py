"""Tests for the request-free task-execution service (ADR-0024).

Covers the agent guards that the historic view path does NOT apply:
  - the task-state guard (by_agent only runs state=new),
  - the autonomous-response approval gate for wazuh_response,
  - and that a human (by_agent=False) keeps the historic behaviour.
"""
from unittest.mock import MagicMock, patch

import pytest

from automations.models import Automation, WazuhActiveResponse
from incidents.models import Incident, Task, WazuhResponseExecution
from incidents.services import task_execution as te
from security.models import Organization


@pytest.fixture(autouse=True)
def semaphore_settings(settings):
    settings.SEMAPHORE_URL = "https://semaphore.example.com"
    settings.SEMAPHORE_API_TOKEN = "test-token"
    settings.SEMAPHORE_PROJECT_ID = 1


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(org, staff):
    return Incident.objects.create(
        organization=org, title="T", display_id="INC-TEST-0001", severity="high",
    )


@pytest.fixture
def automation(db, staff):
    return Automation.objects.create(name="Scan", semaphore_template_id=42, created_by=staff)


@pytest.fixture
def automated_task(incident, automation):
    return Task.objects.create(
        incident=incident, title="Run scan", task_type=Task.TYPE_AUTOMATED, automation=automation,
    )


def _wazuh_response(approved=False, **kw):
    return WazuhActiveResponse.objects.create(
        name="Isolate", command="firewall-drop", autonomous_triage_approved=approved, **kw
    )


@pytest.fixture
def wazuh_task(incident):
    return Task.objects.create(
        incident=incident, title="Isolate host",
        task_type=Task.TYPE_WAZUH_RESPONSE, wazuh_response=_wazuh_response(),
    )


# ── manual tasks ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_manual_task_never_runs(incident):
    task = Task.objects.create(incident=incident, title="Investigate", task_type=Task.TYPE_MANUAL)
    with pytest.raises(te.TaskExecutionError) as exc:
        te.run_task(task, actor=None, by_agent=True)
    assert exc.value.code == "not_executable"


# ── task-state guard (agent only) ────────────────────────────────────────────


@pytest.mark.django_db
def test_agent_skips_already_executed_task(automated_task):
    automated_task.state = Task.STATE_DONE
    automated_task.save(update_fields=["state"])
    with pytest.raises(te.TaskExecutionError) as exc:
        te.run_task(automated_task, actor=None, by_agent=True)
    assert exc.value.code == "already_executed"
    assert exc.value.http_status == 409


@pytest.mark.django_db
def test_agent_runs_new_automated_task(automated_task):
    mock_client = MagicMock()
    mock_client.launch_job.return_value = 9999
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        task = te.run_task(automated_task, actor=None, by_agent=True)
    assert task.state == Task.STATE_IN_PROGRESS
    assert task.semaphore_task_id == 9999


# ── autonomous-response approval gate (agent only) ───────────────────────────


@pytest.mark.django_db
def test_agent_refused_unapproved_wazuh_response(wazuh_task):
    with pytest.raises(te.TaskExecutionError) as exc:
        te.run_task(wazuh_task, actor=None, by_agent=True)
    assert exc.value.code == "not_approved"
    assert exc.value.http_status == 403
    wazuh_task.refresh_from_db()
    assert wazuh_task.state == Task.STATE_NEW
    assert not WazuhResponseExecution.objects.exists()


@pytest.mark.django_db
def test_agent_runs_approved_wazuh_response(incident):
    task = Task.objects.create(
        incident=incident, title="Isolate", task_type=Task.TYPE_WAZUH_RESPONSE,
        wazuh_response=_wazuh_response(approved=True),
    )
    mock_client = MagicMock()
    mock_client.run_active_response.return_value = (200, {"ok": True})
    with patch("security.wazuh.WazuhClient", return_value=mock_client):
        result = te.run_task(task, actor=None, by_agent=True)
    assert result.state == Task.STATE_DONE
    execution = WazuhResponseExecution.objects.get()
    assert execution.executed_by is None  # autonomous
    assert mock_client.run_active_response.called


@pytest.mark.django_db
def test_human_can_run_unapproved_wazuh_response(wazuh_task, staff):
    """A human (by_agent=False) is never blocked by the approval gate or state guard."""
    mock_client = MagicMock()
    mock_client.run_active_response.return_value = (200, {"ok": True})
    with patch("security.wazuh.WazuhClient", return_value=mock_client):
        result = te.run_task(wazuh_task, actor=staff, by_agent=False)
    assert result.state == Task.STATE_DONE
    assert WazuhResponseExecution.objects.get().executed_by == staff


@pytest.mark.django_db
def test_semaphore_failure_raises_502(automated_task):
    from automations.semaphore import SemaphoreAPIError

    mock_client = MagicMock()
    mock_client.launch_job.side_effect = SemaphoreAPIError(500, "boom")
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        with pytest.raises(te.TaskExecutionError) as exc:
            te.run_task(automated_task, actor=None, by_agent=True)
    assert exc.value.http_status == 502
