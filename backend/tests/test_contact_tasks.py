"""Templated contact task (#721).

A task-template item can be a "contact" flavor carrying a role + body template.
Applying it materialises a contact-type Task; running that task emails the
incident's contacts (via the existing contact-messaging path) and/or ad-hoc
custom addresses with the template-rendered body.
"""
from unittest.mock import patch

import pytest

from contacts.models import Contact, ContactMessage, IncidentContact
from incidents.models import Incident, Subject, Task, TaskTemplate, TaskTemplateItem
from incidents.serializers import TaskTemplateItemWriteSerializer
from incidents.services import task_execution
from incidents.services.templates import apply_template
from security.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


def make_incident(org, subject=None):
    return Incident.objects.create(
        organization=org, title="Suspicious login", display_id="INC-2026-0001",
        severity="high", tlp="amber", subject=subject,
    )


def make_contact(org, email="carol@example.com", name="Carol"):
    return Contact.objects.create(organisation=org, name=name, email=email)


def make_contact_template(subject, role="notified", body="Hi, re {{ display_id }}: {{ title }}."):
    t = TaskTemplate.objects.create(name="Notify Contacts", subject=subject)
    TaskTemplateItem.objects.create(
        template=t, title="Email the contact", display_order=1,
        is_contact_task=True, contact_role=role, contact_body=body,
    )
    return t


# ── item validation ───────────────────────────────────────────────────────────

def test_write_serializer_rejects_contact_plus_automation():
    ser = TaskTemplateItemWriteSerializer(data={
        "title": "x", "display_order": 1, "automation": None,
        "is_contact_task": True, "contact_body": "hi",
    })
    # is_contact_task with a body alone is valid
    assert ser.is_valid(), ser.errors


def test_write_serializer_rejects_two_flavors(acme):
    from incidents.models import WazuhActiveResponse
    wr = WazuhActiveResponse.objects.create(name="iso", command="iso", default_args="")
    ser = TaskTemplateItemWriteSerializer(data={
        "title": "x", "display_order": 1, "wazuh_response": wr.id,
        "is_contact_task": True, "contact_body": "hi",
    })
    assert not ser.is_valid()


def test_write_serializer_requires_body_for_contact():
    ser = TaskTemplateItemWriteSerializer(data={
        "title": "x", "display_order": 1, "is_contact_task": True, "contact_body": "   ",
    })
    assert not ser.is_valid()
    assert "contact_body" in ser.errors


# ── materialisation ────────────────────────────────────────────────────────────

def test_apply_template_creates_contact_task(acme, phishing, staff):
    inc = make_incident(acme, subject=phishing)
    template = make_contact_template(phishing, role="questioned", body="Body {{ display_id }}")
    apply_template(inc, template, staff)

    task = Task.objects.get(incident=inc)
    assert task.task_type == Task.TYPE_CONTACT
    assert task.contact_role == "questioned"
    assert task.contact_body == "Body {{ display_id }}"


# ── recipient defaulting ───────────────────────────────────────────────────────

def test_default_recipients_are_incident_linked_contacts(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=contact)

    recips = task_execution.resolve_default_contact_recipients(inc)
    assert recips == [{"contact_id": contact.id, "name": "Carol", "email": "carol@example.com"}]


# ── execution ──────────────────────────────────────────────────────────────────

def _contact_task(inc, role="notified", body="Re {{ display_id }} ({{ severity }}): {{ title }}"):
    return Task.objects.create(
        incident=inc, title="Email", task_type=Task.TYPE_CONTACT,
        contact_role=role, contact_body=body,
    )


def test_execute_sends_to_contact_via_messaging_path(acme, staff):
    inc = make_incident(acme)
    contact = make_contact(acme)
    task = _contact_task(inc)

    with patch("contacts.services.send_html_email") as mock_send:
        task = task_execution.execute_contact_task(task, actor=staff, contact_ids=[contact.id])

    # An outbound ContactMessage was recorded and the email dispatched.
    assert ContactMessage.objects.filter(incident=inc, contact=contact, direction="outbound").count() == 1
    mock_send.assert_called_once()
    # Body was rendered against the incident.
    sent_context = mock_send.call_args[0][1]
    assert sent_context["message"] == "Re INC-2026-0001 (high): Suspicious login"
    assert task.state == Task.STATE_DONE


def test_execute_sends_to_custom_address_without_contact_record(acme, staff):
    inc = make_incident(acme)
    task = _contact_task(inc)

    with patch("contacts.services.send_html_email") as mock_send:
        task = task_execution.execute_contact_task(task, actor=staff, emails=["ext@vendor.test"])

    assert ContactMessage.objects.filter(incident=inc).count() == 0
    mock_send.assert_called_once()
    assert mock_send.call_args[0][2] == ["ext@vendor.test"]
    assert inc.events.filter(kind="contact_email_sent").count() == 1
    assert task.state == Task.STATE_DONE


def test_execute_mixed_recipients(acme, staff):
    inc = make_incident(acme)
    contact = make_contact(acme)
    task = _contact_task(inc)

    with patch("contacts.services.send_html_email") as mock_send:
        task_execution.execute_contact_task(
            task, actor=staff, contact_ids=[contact.id], emails=["ext@vendor.test"]
        )

    assert mock_send.call_count == 2
    assert ContactMessage.objects.filter(incident=inc, contact=contact).count() == 1


def test_execute_requires_a_recipient(acme, staff):
    inc = make_incident(acme)
    task = _contact_task(inc)
    with pytest.raises(task_execution.TaskExecutionError) as exc:
        task_execution.execute_contact_task(task, actor=staff, contact_ids=[], emails=[])
    assert exc.value.code == "no_recipients"


def test_execute_rejects_foreign_org_contact(acme, staff):
    other = Organization.objects.create(name="Other", slug="other", wazuh_group="other")
    inc = make_incident(acme)
    foreign = make_contact(other, email="x@other.test")
    task = _contact_task(inc)
    with pytest.raises(task_execution.TaskExecutionError) as exc:
        task_execution.execute_contact_task(task, actor=staff, contact_ids=[foreign.id])
    assert exc.value.code == "bad_recipient"


def test_agent_may_not_send_contact_task(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)
    task = _contact_task(inc)
    with pytest.raises(task_execution.TaskExecutionError) as exc:
        task_execution.run_task(task, actor=None, by_agent=True, contact_ids=[contact.id])
    assert exc.value.code == "not_executable_by_agent"


# ── run endpoint ───────────────────────────────────────────────────────────────

def test_run_endpoint_sends_contact_task(admin_client, acme):
    inc = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=contact)
    task = _contact_task(inc)

    with patch("contacts.services.send_html_email"):
        resp = admin_client.post(
            f"/api/tasks/{task.id}/run/",
            data={"contact_ids": [contact.id]},
            content_type="application/json",
        )
    assert resp.status_code == 200, resp.content
    assert resp.json()["state"] == "done"


def test_preview_endpoint_returns_defaults_and_rendered_body(admin_client, acme):
    inc = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=contact)
    task = _contact_task(inc)

    resp = admin_client.get(f"/api/tasks/{task.id}/preview/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "notified"
    assert data["rendered_body"] == "Re INC-2026-0001 (high): Suspicious login"
    assert data["default_recipients"] == [
        {"contact_id": contact.id, "name": "Carol", "email": "carol@example.com"}
    ]
