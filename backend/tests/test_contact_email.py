import pytest
from unittest.mock import patch

from contacts.models import Contact, ContactMessage
from contacts.services import send_contact_message
from contacts.tokens import sign_contact_reply_token, unsign_contact_reply_token, build_reply_to_address
from incidents.models import Incident
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_incident(org):
    return Incident.objects.create(
        organization=org, title="Test", display_id="INC-2026-0001", tlp="amber"
    )


def make_contact(org):
    return Contact.objects.create(organisation=org, name="Carol", email="carol@example.com")


# ── Token round-trip ──────────────────────────────────────────────────────────

def test_token_round_trip():
    token = sign_contact_reply_token(42, 7)
    inc_id, contact_id = unsign_contact_reply_token(token)
    assert inc_id == 42
    assert contact_id == 7


def test_build_reply_to_address_contains_token():
    addr = build_reply_to_address(1, 2)
    assert addr.startswith("soc+")
    assert "@" in addr
    token = addr.split("soc+")[1].split("@")[0]
    inc_id, contact_id = unsign_contact_reply_token(token)
    assert inc_id == 1
    assert contact_id == 2


# ── send_contact_message ──────────────────────────────────────────────────────

@pytest.mark.django_db
def test_send_notified_uses_correct_template(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)

    with patch("contacts.services.send_html_email") as mock_send:
        send_contact_message(inc, contact, "notified", "FYI.")

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[0][0] == "contact_notified"
    assert call_args[0][2] == ["carol@example.com"]
    assert "reply_to" not in call_args[1]


@pytest.mark.django_db
def test_send_questioned_uses_correct_template_and_reply_to(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)

    with patch("contacts.services.send_html_email") as mock_send:
        send_contact_message(inc, contact, "questioned", "Did you do this?")

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[0][0] == "contact_questioned"
    reply_to = call_args[1].get("reply_to", [])
    assert len(reply_to) == 1
    assert reply_to[0].startswith("soc+")


@pytest.mark.django_db
def test_send_contact_message_creates_outbound_record(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)

    with patch("contacts.services.send_html_email"):
        msg = send_contact_message(inc, contact, "notified", "Hello.")

    assert msg.direction == ContactMessage.DIRECTION_OUTBOUND
    assert msg.role == "notified"
    assert msg.body == "Hello."
    assert ContactMessage.objects.filter(incident=inc, contact=contact).count() == 1


@pytest.mark.django_db
def test_send_contact_message_context_contains_body(acme):
    inc = make_incident(acme)
    contact = make_contact(acme)

    with patch("contacts.services.send_html_email") as mock_send:
        send_contact_message(inc, contact, "questioned", "Hello?")

    context = mock_send.call_args[0][1]
    assert context["message"] == "Hello?"
    assert context["contact_name"] == "Carol"
    assert context["display_id"] == "INC-2026-0001"
