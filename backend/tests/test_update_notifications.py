"""Tests for all-updates contact notifications (ADR-0034 / #710)."""
from unittest.mock import MagicMock, patch

import pytest

from contacts.models import Contact, ContactMessage, IncidentContact
from contacts.services import send_contact_message
from incidents.models import Comment, Incident
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass", is_staff=True)


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_incident(org, tlp="green", n=1):
    return Incident.objects.create(
        organization=org, title="Phish", display_id=f"INC-2026-{n:04d}", tlp=tlp,
        description="Suspicious email",
    )


def make_contact(org, email="c@acme.com"):
    return Contact.objects.create(organisation=org, name="Carol", email=email)


def link(incident, contact, level):
    return IncidentContact.objects.create(incident=incident, contact=contact, notify_level=level)


def user_comment(incident, body="Here is an update for you.", is_internal=False):
    return Comment.objects.create(incident=incident, kind=Comment.KIND_USER, body=body, is_internal=is_internal)


# ── notify_contacts_of_update task ────────────────────────────────────────────


@pytest.mark.django_db
def test_update_notifies_all_updates_contacts_only(acme):
    incident = make_incident(acme, tlp="green")
    all_c = make_contact(acme, email="all@acme.com")
    closure_c = make_contact(acme, email="closure@acme.com")
    link(incident, all_c, IncidentContact.NOTIFY_ALL_UPDATES)
    link(incident, closure_c, IncidentContact.NOTIFY_CLOSURE_ONLY)
    comment = user_comment(incident)

    with patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_of_update
        notify_contacts_of_update(comment.id)

    msgs = ContactMessage.objects.filter(incident=incident, role="update")
    assert msgs.count() == 1
    assert msgs.first().contact_id == all_c.id
    assert msgs.first().body == "Here is an update for you."
    mock_email.assert_called_once()
    assert all_c.email in mock_email.call_args[0][2]


@pytest.mark.django_db
def test_update_skips_internal_comment(acme):
    incident = make_incident(acme, tlp="green")
    all_c = make_contact(acme)
    link(incident, all_c, IncidentContact.NOTIFY_ALL_UPDATES)
    comment = user_comment(incident, is_internal=True)

    with patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_of_update
        notify_contacts_of_update(comment.id)

    assert not ContactMessage.objects.filter(incident=incident).exists()
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_update_skips_non_user_comment(acme):
    incident = make_incident(acme, tlp="green")
    all_c = make_contact(acme)
    link(incident, all_c, IncidentContact.NOTIFY_ALL_UPDATES)
    comment = Comment.objects.create(
        incident=incident, kind=Comment.KIND_AI_TRIAGE, body="triage", is_internal=False
    )

    with patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_of_update
        notify_contacts_of_update(comment.id)

    assert not ContactMessage.objects.filter(incident=incident).exists()
    mock_email.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("tlp", ["amber", "red"])
def test_update_skips_amber_and_red(acme, tlp):
    incident = make_incident(acme, tlp=tlp)
    all_c = make_contact(acme)
    link(incident, all_c, IncidentContact.NOTIFY_ALL_UPDATES)
    comment = user_comment(incident)

    with patch("contacts.services.send_html_email") as mock_email:
        from incidents.tasks import notify_contacts_of_update
        notify_contacts_of_update(comment.id)

    assert not ContactMessage.objects.filter(incident=incident).exists()
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_update_records_contact_message_event(acme):
    incident = make_incident(acme, tlp="green")
    all_c = make_contact(acme)
    link(incident, all_c, IncidentContact.NOTIFY_ALL_UPDATES)
    comment = user_comment(incident)

    with patch("contacts.services.send_html_email"):
        from incidents.tasks import notify_contacts_of_update
        notify_contacts_of_update(comment.id)

    assert incident.events.filter(kind="contact_message_sent").exists()


# ── send routing / template ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_send_update_uses_contact_update_template(acme):
    incident = make_incident(acme, tlp="green")
    contact = make_contact(acme)

    with patch("contacts.services.send_html_email") as mock_send:
        send_contact_message(incident, contact, "update", "A fresh update.")

    args = mock_send.call_args
    assert args[0][0] == "contact_update"
    assert "reply_to" not in args[1]


@pytest.mark.django_db
def test_contact_update_template_renders_comment_body():
    from notifications.email import render_email

    subject, html, plain = render_email("contact_update", {
        "contact_name": "Carol",
        "display_id": "INC-2026-0001",
        "title": "Phish",
        "description": "Suspicious email",
        "message": "We blocked the malicious sender.",
        "frontend_url": "https://app.example.com",
    })
    assert "We blocked the malicious sender." in html
    assert "INC-2026-0001" in html


# ── comment-create dispatch wiring ────────────────────────────────────────────


@pytest.mark.django_db
def test_comment_create_dispatches_update_task(client, acme_member, acme):
    incident = make_incident(acme, tlp="green")
    client.force_login(acme_member)

    with patch("incidents.tasks.notify_contacts_of_update") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(
            f"/api/incidents/{incident.display_id}/comments/",
            {"body": "An update", "is_internal": False},
            content_type="application/json",
        )

    assert resp.status_code == 201
    comment_id = resp.json()["id"]
    mock_task.delay.assert_called_once_with(comment_id)
