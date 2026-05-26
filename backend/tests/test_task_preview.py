import pytest

from automations.models import Automation
from incidents.models import Asset, IOC, Incident, Task
from security.models import Organization


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
        title="Preview Incident",
        display_id="INC-PRV-0001",
        severity="medium",
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


def _preview_url(pk):
    return f"/api/tasks/{pk}/preview/"


# ── auth guards ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_preview_returns_403_for_non_staff(client, regular_user, automated_task):
    client.force_login(regular_user)
    resp = client.get(_preview_url(automated_task.pk))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_preview_returns_404_for_unknown_task(client, staff):
    client.force_login(staff)
    resp = client.get(_preview_url(99999))
    assert resp.status_code == 404


# ── successful resolution ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_preview_returns_vars_dict(client, staff, automated_task, incident):
    automated_task.automation.default_vars = "timeout: 30"
    automated_task.automation.save()

    client.force_login(staff)
    resp = client.get(_preview_url(automated_task.pk))

    assert resp.status_code == 200
    data = resp.json()
    assert "vars" in data
    assert data["vars"]["timeout"] == 30
    assert data["vars"]["incident_title"] == incident.title
    assert data["vars"]["incident_severity"] == incident.severity


@pytest.mark.django_db
def test_preview_with_no_mappings_returns_default_and_hardcoded(client, staff, automated_task, incident):
    client.force_login(staff)
    resp = client.get(_preview_url(automated_task.pk))

    assert resp.status_code == 200
    v = resp.json()["vars"]
    assert v["incident_id"] == incident.id
    assert v["incident_display_id"] == incident.display_id


@pytest.mark.django_db
def test_preview_resolves_incident_var_mappings(client, staff, automated_task, incident, org):
    asset = Asset.objects.create(
        organization=org, kind="host", name="Host1", agent_name="wazuh-preview"
    )
    incident.assets.add(asset)
    ioc = IOC.objects.create(incident=incident, kind="ip", value="1.2.3.4")

    automated_task.automation.incident_var_mappings = (
        "- {var: hosts, source: assets.agent_name}\n"
        "- {var: block_ips, source: iocs.ip, format: comma_separated}"
    )
    automated_task.automation.save()

    client.force_login(staff)
    resp = client.get(_preview_url(automated_task.pk))

    assert resp.status_code == 200
    v = resp.json()["vars"]
    assert v["hosts"] == "wazuh-preview"
    assert v["block_ips"] == "1.2.3.4"


# ── zero-values error ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_preview_returns_400_with_error_key_on_zero_values(client, staff, automated_task, incident):
    automated_task.automation.incident_var_mappings = "- {var: hosts, source: assets.agent_name}"
    automated_task.automation.save()

    client.force_login(staff)
    resp = client.get(_preview_url(automated_task.pk))

    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert "hosts" in data["error"]
