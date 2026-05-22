import pytest
from unittest.mock import MagicMock, patch, call
from django.core.signing import BadSignature, SignatureExpired

from contacts.models import Contact, ContactMessage, IncidentContact
from contacts.tokens import sign_contact_reply_token
from incidents.models import Comment, Incident
from inbound_mail.dataclasses import NormalisedMessage
from inbound_mail.adapters import ImapAdapter, _extract_body
from inbound_mail.handlers import ContactReplyHandler, _extract_token
from inbound_mail.router import route_inbound_message
from security.models import Organization, OrganizationMembership


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(acme):
    return Incident.objects.create(
        organization=acme, title="Test", display_id="INC-2026-0001", tlp="amber"
    )


@pytest.fixture
def contact(acme):
    return Contact.objects.create(organisation=acme, name="Carol", email="carol@example.com")


def make_message(to_address="soc@example.com", body_text="Hello", subject="Re: incident"):
    return NormalisedMessage(
        from_address="carol@example.com",
        to_address=to_address,
        reply_to=None,
        subject=subject,
        body_text=body_text,
        body_html="",
    )


# ── Token extraction ──────────────────────────────────────────────────────────

def test_extract_token_with_plus():
    assert _extract_token("soc+mytoken@example.com") == "mytoken"


def test_extract_token_without_plus():
    assert _extract_token("soc@example.com") is None


def test_extract_token_none():
    assert _extract_token(None) is None


# ── ImapAdapter — no env vars ─────────────────────────────────────────────────

def test_imap_adapter_noop_when_no_env(monkeypatch):
    for k in ("INBOUND_IMAP_HOST", "INBOUND_IMAP_USER", "INBOUND_IMAP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    adapter = ImapAdapter()
    messages = list(adapter.fetch_unseen())
    assert messages == []


# ── ImapAdapter — with mocked IMAP ───────────────────────────────────────────

def _build_raw_email(from_addr="carol@example.com", to_addr="soc+tok@example.com",
                     subject="Re: incident", body="Hello world"):
    import email.mime.text
    msg = email.mime.text.MIMEText(body, "plain", "utf-8")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    return msg.as_bytes()


def test_imap_adapter_fetches_and_marks_seen(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("INBOUND_IMAP_USER", "user")
    monkeypatch.setenv("INBOUND_IMAP_PASSWORD", "pass")

    raw = _build_raw_email()
    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b"1"])
    mock_conn.fetch.return_value = (None, [(None, raw)])

    with patch("inbound_mail.adapters.imaplib.IMAP4_SSL", return_value=mock_conn):
        adapter = ImapAdapter()
        messages = list(adapter.fetch_unseen())

    assert len(messages) == 1
    msg = messages[0]
    assert msg.from_address == "carol@example.com"
    assert msg.to_address == "soc+tok@example.com"
    assert "Hello world" in msg.body_text
    mock_conn.store.assert_called_once_with(b"1", "+FLAGS", "\\Seen")


def test_imap_adapter_empty_mailbox(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("INBOUND_IMAP_USER", "user")
    monkeypatch.setenv("INBOUND_IMAP_PASSWORD", "pass")

    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b""])

    with patch("inbound_mail.adapters.imaplib.IMAP4_SSL", return_value=mock_conn):
        adapter = ImapAdapter()
        messages = list(adapter.fetch_unseen())

    assert messages == []


# ── ContactReplyHandler ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_handler_creates_contact_message_on_valid_token(incident, contact):
    token = sign_contact_reply_token(incident.id, contact.id)
    msg = make_message(to_address=f"soc+{token}@example.com", body_text="I saw that")

    ContactReplyHandler().handle(msg)

    messages = ContactMessage.objects.filter(incident=incident)
    assert messages.count() == 1
    cm = messages.first()
    assert cm.direction == ContactMessage.DIRECTION_INBOUND
    assert cm.body == "I saw that"
    assert cm.contact == contact
    assert cm.parent is None


@pytest.mark.django_db
def test_handler_sets_parent_to_most_recent_outbound(incident, contact):
    outbound = ContactMessage.objects.create(
        incident=incident,
        contact=contact,
        direction=ContactMessage.DIRECTION_OUTBOUND,
        role="questioned",
        body="Did you see this?",
    )
    token = sign_contact_reply_token(incident.id, contact.id)
    msg = make_message(to_address=f"soc+{token}@example.com", body_text="Yes I did")

    ContactReplyHandler().handle(msg)

    cm = ContactMessage.objects.get(incident=incident, direction=ContactMessage.DIRECTION_INBOUND)
    assert cm.parent == outbound


@pytest.mark.django_db
def test_handler_uses_subject_when_body_empty(incident, contact):
    token = sign_contact_reply_token(incident.id, contact.id)
    msg = make_message(to_address=f"soc+{token}@example.com", body_text="", subject="My reply")

    ContactReplyHandler().handle(msg)

    cm = ContactMessage.objects.get(incident=incident, direction=ContactMessage.DIRECTION_INBOUND)
    assert cm.body == "My reply"


@pytest.mark.django_db
def test_handler_invalid_token_does_not_raise(caplog):
    msg = make_message(to_address="soc+BADTOKEN@example.com")
    ContactReplyHandler().handle(msg)
    assert ContactMessage.objects.count() == 0


@pytest.mark.django_db
def test_handler_expired_token_does_not_raise(incident, contact):
    token = sign_contact_reply_token(incident.id, contact.id)
    msg = make_message(to_address=f"soc+{token}@example.com")

    with patch("inbound_mail.handlers.unsign_contact_reply_token", side_effect=SignatureExpired("expired")):
        ContactReplyHandler().handle(msg)

    assert ContactMessage.objects.count() == 0


@pytest.mark.django_db
def test_handler_no_plus_suffix_does_not_raise():
    msg = make_message(to_address="soc@example.com")
    ContactReplyHandler().handle(msg)
    assert ContactMessage.objects.count() == 0


# ── route_inbound_message ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_route_no_plus_suffix_logs_and_drops(caplog):
    msg = make_message(to_address="soc@example.com")
    route_inbound_message(msg)
    assert ContactMessage.objects.count() == 0


@pytest.mark.django_db
def test_route_with_token_delegates_to_handler(incident, contact):
    token = sign_contact_reply_token(incident.id, contact.id)
    msg = make_message(to_address=f"soc+{token}@example.com", body_text="Hi there")

    route_inbound_message(msg)

    assert ContactMessage.objects.filter(
        incident=incident, direction=ContactMessage.DIRECTION_INBOUND
    ).count() == 1
