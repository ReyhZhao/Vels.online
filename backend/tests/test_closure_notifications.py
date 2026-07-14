"""Tests for closure contact notifications (#388, reworked for ADR-0034 tiering / #709)."""
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


def make_incident(org, state="in_progress", tlp="green"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Phishing test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
        tlp=tlp,
        description="Suspicious email from attacker@evil.com",
    )


def make_contact(org, email="reporter@acme.com"):
    return Contact.objects.create(organisation=org, name="Alice Reporter", email=email)


# ── WHITE/GREEN: full LLM summary ─────────────────────────────────────────────


@pytest.mark.django_db
def test_green_closure_sends_llm_summary(acme):
    incident = make_incident(acme, tlp="green")
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()
    mock_provider.generate_closure_message.return_value = "We investigated and closed the case."

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    msg = ContactMessage.objects.get(incident=incident, contact=contact, role="notified")
    assert msg.body == "We investigated and closed the case."
    mock_email.assert_called_once()
    assert contact.email in mock_email.call_args[0][2]


@pytest.mark.django_db
def test_green_closure_summary_grounding_includes_triage_excludes_other_internal(acme):
    incident = make_incident(acme, tlp="green")
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    # Included: non-internal user comment + internal AI-triage comment.
    Comment.objects.create(incident=incident, kind=Comment.KIND_USER,
                           body="Customer-facing note about the phish.", is_internal=False)
    Comment.objects.create(incident=incident, kind=Comment.KIND_AI_TRIAGE,
                           body="Triage: known threat actor, credential phish.", is_internal=True)
    # Excluded: an internal analyst note that is NOT triage.
    Comment.objects.create(incident=incident, kind=Comment.KIND_USER,
                           body="INTERNAL: this customer clicks everything.", is_internal=True)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    captured = {}
    mock_provider = MagicMock()
    def capture(ctx):
        captured.update(ctx)
        return "Closed."
    mock_provider.generate_closure_message.side_effect = capture

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email"):
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    comments = captured["comments"]
    assert "Customer-facing note about the phish." in comments
    assert "Triage: known threat actor, credential phish." in comments
    assert "INTERNAL: this customer clicks everything." not in comments


@pytest.mark.django_db
def test_green_closure_multiple_contacts(acme):
    incident = make_incident(acme, tlp="white")
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
def test_green_closure_llm_failure_does_not_create_messages(acme):
    incident = make_incident(acme, tlp="green")
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


# ── AMBER: bare notice, no summary, no LLM call ───────────────────────────────


@pytest.mark.django_db
def test_amber_closure_sends_bare_notice_without_llm(acme):
    incident = make_incident(acme, tlp="amber")
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    # Bare notice: message recorded is empty, no LLM call, but email still sent.
    msg = ContactMessage.objects.get(incident=incident, contact=contact, role="notified")
    assert msg.body == ""
    mock_provider.generate_closure_message.assert_not_called()
    mock_email.assert_called_once()


# ── RED: nothing at all ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_red_closure_sends_nothing(acme):
    incident = make_incident(acme, tlp="red")
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact)
    incident.state = "closed"
    incident.closure_reason = "resolved"
    incident.save()

    mock_provider = MagicMock()

    with patch("incidents.tasks.get_closure_provider", return_value=mock_provider), \
         patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_on_close
        notify_contacts_on_close(incident.id)

    assert not ContactMessage.objects.filter(incident=incident).exists()
    mock_provider.generate_closure_message.assert_not_called()
    mock_email.assert_not_called()


# ── no contacts / dispatch wiring ─────────────────────────────────────────────


@pytest.mark.django_db
def test_closure_no_contacts_is_noop(acme):
    incident = make_incident(acme, tlp="green")
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
