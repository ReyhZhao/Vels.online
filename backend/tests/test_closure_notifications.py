"""Tests for #388: closure contact notifications and phishing drop notifications."""
from unittest.mock import MagicMock, patch

import pytest

from contacts.models import Contact, ContactMessage, IncidentContact
from incidents.models import Comment, Incident
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def actor(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


def make_incident(org, state="in_progress"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Phishing test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
        description="Suspicious email from attacker@evil.com",
    )


def make_contact(org, email="reporter@acme.com"):
    return Contact.objects.create(organisation=org, name="Alice Reporter", email=email)


# ── notify_contacts_on_close task ────────────────────────────────────────────


@pytest.mark.django_db
def test_closure_notification_sent_to_linked_contacts(acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()
    mock_provider.generate_closure_message.return_value = "We have investigated and closed the case."

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    assert ContactMessage.objects.filter(
        incident=incident, contact=contact, role="notified"
    ).exists()
    mock_email.assert_called_once()
    args = mock_email.call_args
    assert contact.email in args[0][2]


@pytest.mark.django_db
def test_closure_notification_multiple_contacts(acme):
    incident = make_incident(acme)
    c1 = make_contact(acme, email="alice@acme.com")
    c2 = make_contact(acme, email="bob@acme.com")
    IncidentContact.objects.create(incident=incident, contact=c1)
    IncidentContact.objects.create(incident=incident, contact=c2)
    incident.state = "closed"
    incident.closure_reason = "false_positive"
    incident.save()

    mock_provider = MagicMock()
    mock_provider.generate_closure_message.return_value = "No threat found."

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email"):
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    assert ContactMessage.objects.filter(incident=incident, role="notified").count() == 2


@pytest.mark.django_db
def test_closure_notification_llm_failure_does_not_create_messages(acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()
    mock_provider.generate_closure_message.side_effect = Exception("Gemini down")

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    assert not ContactMessage.objects.filter(incident=incident).exists()
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_closure_notification_no_contacts_is_noop(acme):
    incident = make_incident(acme)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    mock_provider.generate_closure_message.assert_not_called()
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_closure_notification_includes_ai_triage_in_context(acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    Comment.objects.create(
        incident=incident,
        kind=Comment.KIND_AI_TRIAGE,
        body="This appears to be a phishing attempt from a known threat actor.",
        is_internal=True,
    )
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    captured_context = {}
    mock_provider = MagicMock()
    def capture_context(ctx):
        captured_context.update(ctx)
        return "Closed."
    mock_provider.generate_closure_message.side_effect = capture_context

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email"):
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    assert captured_context["closure_reason"] == "resolved"
    assert "This appears to be a phishing attempt" in captured_context["ai_triage_summaries"][0]


@pytest.mark.django_db
def test_transition_to_closed_dispatches_notify_task(acme, actor):
    incident = make_incident(acme)

    with patch("incidents.tasks.notify_contacts_on_close") as mock_task:
        mock_task.delay = MagicMock()
        from incidents.services.transitions import transition_incident
        transition_incident(incident, "closed", actor=actor, closure_reason="resolved")

    mock_task.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_transition_to_non_closed_does_not_dispatch_notify_task(acme, actor):
    incident = make_incident(acme, state="new")

    with patch("incidents.tasks.notify_contacts_on_close") as mock_task:
        mock_task.delay = MagicMock()
        from incidents.services.transitions import transition_incident
        transition_incident(incident, "triaged", actor=actor)

    mock_task.delay.assert_not_called()
