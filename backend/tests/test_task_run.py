from unittest.mock import MagicMock, patch

import pytest

from automations.models import Automation
from incidents.models import Asset, IOC, Incident, Task
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
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="user", password="pass")


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def automation(db, staff):
    return Automation.objects.create(
        name="Malware Scan",
        semaphore_template_id=42,
        created_by=staff,
    )


@pytest.fixture
def incident(org, staff):
    return Incident.objects.create(
        organization=org,
        title="Test Incident",
        display_id="INC-TEST-0001",
        severity="high",
        assignee=staff,
    )


@pytest.fixture
def automated_task(incident, automation):
    return Task.objects.create(
        incident=incident,
        title="Run scan",
        task_type=Task.TYPE_AUTOMATED,
        automation=automation,
    )


def _run_url(pk):
    return f"/api/tasks/{pk}/run/"


# ── auth and type guards ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_requires_staff(client, regular_user, automated_task):
    client.force_login(regular_user)
    resp = client.post(_run_url(automated_task.pk), content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_run_returns_404_for_unknown_task(client, staff):
    client.force_login(staff)
    resp = client.post(_run_url(99999), content_type="application/json")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_run_rejects_manual_task(client, staff, incident):
    task = Task.objects.create(incident=incident, title="Manual", task_type=Task.TYPE_MANUAL)
    client.force_login(staff)
    resp = client.post(_run_url(task.pk), content_type="application/json")
    assert resp.status_code == 400


# ── default_vars from YAML ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_passes_yaml_default_vars_to_semaphore(client, staff, automated_task):
    automated_task.automation.default_vars = "scan_mode: quick\nretries: 3"
    automated_task.automation.save()

    mock_client = MagicMock()
    mock_client.launch_job.return_value = 77
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert extra_vars["scan_mode"] == "quick"
    assert extra_vars["retries"] == 3


@pytest.mark.django_db
def test_run_without_default_vars(client, staff, automated_task):
    mock_client = MagicMock()
    mock_client.launch_job.return_value = 55
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert "incident_id" in extra_vars


# ── hardcoded incident fields always present ──────────────────────────────────


@pytest.mark.django_db
def test_run_always_includes_hardcoded_incident_fields(client, staff, automated_task, incident):
    mock_client = MagicMock()
    mock_client.launch_job.return_value = 1
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert extra_vars["incident_id"] == incident.id
    assert extra_vars["incident_display_id"] == incident.display_id
    assert extra_vars["incident_title"] == incident.title
    assert extra_vars["incident_severity"] == incident.severity


# ── incident_var_mappings resolved ────────────────────────────────────────────


@pytest.mark.django_db
def test_run_resolves_incident_var_mappings(client, staff, automated_task, incident, org):
    asset = Asset.objects.create(
        organization=org, kind="host", name="Agent1", agent_name="wazuh-agent-1"
    )
    incident.assets.add(asset)

    automated_task.automation.incident_var_mappings = "- {var: hosts, source: assets.agent_name}"
    automated_task.automation.save()

    mock_client = MagicMock()
    mock_client.launch_job.return_value = 10
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert extra_vars["hosts"] == "wazuh-agent-1"


@pytest.mark.django_db
def test_run_resolved_mappings_overwrite_default_vars(client, staff, automated_task, incident, org):
    asset = Asset.objects.create(
        organization=org, kind="host", name="Agent1", agent_name="resolved-agent"
    )
    incident.assets.add(asset)

    automated_task.automation.default_vars = "hosts: default-host"
    automated_task.automation.incident_var_mappings = "- {var: hosts, source: assets.agent_name}"
    automated_task.automation.save()

    mock_client = MagicMock()
    mock_client.launch_job.return_value = 11
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert extra_vars["hosts"] == "resolved-agent"


@pytest.mark.django_db
def test_run_hardcoded_fields_overwrite_mappings(client, staff, automated_task, incident, org):
    # incident.title is a hardcoded field; even if mapped, hardcoded layer wins
    automated_task.automation.default_vars = "incident_title: overridden-title"
    automated_task.automation.save()

    mock_client = MagicMock()
    mock_client.launch_job.return_value = 12
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 200
    extra_vars = mock_client.launch_job.call_args[1]["extra_vars"]
    assert extra_vars["incident_title"] == incident.title


# ── zero-values error returns 400 ─────────────────────────────────────────────


@pytest.mark.django_db
def test_run_returns_400_when_resolver_raises(client, staff, automated_task, incident):
    # No assets linked → assets.agent_name resolves to nothing
    automated_task.automation.incident_var_mappings = "- {var: hosts, source: assets.agent_name}"
    automated_task.automation.save()

    client.force_login(staff)
    resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 400
    assert "hosts" in resp.json()["detail"]


# ── semaphore errors surface as 502 ──────────────────────────────────────────


@pytest.mark.django_db
def test_run_returns_502_on_semaphore_error(client, staff, automated_task):
    from automations.semaphore import SemaphoreAPIError

    mock_client = MagicMock()
    mock_client.launch_job.side_effect = SemaphoreAPIError(500, "boom")
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(_run_url(automated_task.pk), content_type="application/json")

    assert resp.status_code == 502
