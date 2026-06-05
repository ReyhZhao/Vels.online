"""Tests for #318: PhishingIngestionHandler and router wiring."""
import email
import email.mime.multipart
import email.mime.text
import email.mime.base
from unittest.mock import patch, MagicMock

import pytest

from alerts.models import Alert
from incidents.models import Incident
from inbound_mail.dataclasses import NormalisedAttachment, NormalisedMessage
from inbound_mail.handlers import PhishingIngestionHandler
from inbound_mail.router import route_inbound_message
from security.models import Organization, OrganizationMembership


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def forwarder(acme):
    from django.contrib.auth.models import User
    user = User.objects.create_user(username="carol", email="carol@acme.com", password="x")
    OrganizationMembership.objects.create(user=user, organization=acme)
    return user


def _rfc822_attachment(inner_from="phisher@evil.com"):
    inner = email.mime.text.MIMEText("Click here!", "plain")
    inner["From"] = inner_from
    inner["Subject"] = "Win a prize"
    return NormalisedAttachment(
        filename="",
        content_type="message/rfc822",
        payload=inner.as_bytes(),
    )


def _forwarded_msg(forwarder_email="carol@acme.com", to="soc@vels.online"):
    return NormalisedMessage(
        from_address=forwarder_email,
        to_address=to,
        reply_to=None,
        subject="Fwd: Win a prize",
        body_text="FYI\n---------- Forwarded message ---------\nFrom: phisher@evil.com\n",
        body_html="",
        raw_bytes=b"raw email bytes",
        attachments=[],
    )


# ── PhishingIngestionHandler ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_happy_path_creates_alert_and_incident(acme, forwarder):
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        PhishingIngestionHandler().handle(msg)

    alert = Alert.objects.get(source_kind="inbound_email")
    assert alert.severity == "high"
    assert alert.organization == acme
    assert alert.incident is not None
    assert alert.incident.source_kind == "inbound_email"


@pytest.mark.django_db
def test_second_forwarded_email_links_to_existing_incident(acme, forwarder):
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        PhishingIngestionHandler().handle(msg)
        PhishingIngestionHandler().handle(msg)

    incidents = Incident.objects.filter(source_kind="inbound_email")
    assert incidents.count() == 1
    assert Alert.objects.filter(source_kind="inbound_email").count() == 2


@pytest.mark.django_db
def test_non_forwarded_email_dropped(acme, forwarder):
    msg = NormalisedMessage(
        from_address="carol@acme.com",
        to_address="soc@vels.online",
        reply_to=None,
        subject="Hello",
        body_text="Not a forwarded email.",
        body_html="",
    )
    PhishingIngestionHandler().handle(msg)
    assert Alert.objects.filter(source_kind="inbound_email").count() == 0


@pytest.mark.django_db
def test_unknown_sender_dropped(acme):
    msg = _forwarded_msg(forwarder_email="stranger@unknown.com")
    PhishingIngestionHandler().handle(msg)
    assert Alert.objects.filter(source_kind="inbound_email").count() == 0


@pytest.mark.django_db
def test_source_ref_contains_required_fields(acme, forwarder):
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        PhishingIngestionHandler().handle(msg)

    alert = Alert.objects.get(source_kind="inbound_email")
    ref = alert.source_ref
    assert "sender_address" in ref
    assert "subject_normalised" in ref
    assert "forwarder_address" in ref
    assert ref["forwarder_address"] == "carol@acme.com"


# ── Router wiring ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_router_routes_bare_soc_to_phishing_handler(acme, forwarder, monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    msg = _forwarded_msg(to="soc@vels.online")

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        route_inbound_message(msg)

    assert Alert.objects.filter(source_kind="inbound_email").count() == 1


@pytest.mark.django_db
def test_router_does_not_route_plus_token_to_phishing(acme, forwarder, monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    from contacts.tokens import sign_contact_reply_token
    from incidents.models import Incident as Inc
    from contacts.models import Contact
    inc = Inc.objects.create(organization=acme, title="T", display_id="INC-2026-0001")
    contact = Contact.objects.create(organisation=acme, name="Dan", email="dan@acme.com")
    token = sign_contact_reply_token(inc.id, contact.id)

    msg = NormalisedMessage(
        from_address="carol@acme.com",
        to_address=f"soc+{token}@vels.online",
        reply_to=None,
        subject="Re: incident",
        body_text="Hello",
        body_html="",
    )
    route_inbound_message(msg)
    assert Alert.objects.filter(source_kind="inbound_email").count() == 0


# ── Extend allow list to contacts (#334) ─────────────────────────────────────

@pytest.mark.django_db
def test_contact_sender_resolves_org(acme):
    from contacts.models import Contact
    Contact.objects.create(organisation=acme, name="Bob", email="bob@client.com")
    msg = _forwarded_msg(forwarder_email="bob@client.com")

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user"):
        result = PhishingIngestionHandler().handle(msg)

    assert result in ("phishing:created", "phishing:dedup")
    assert Alert.objects.filter(source_kind="inbound_email").count() == 1


@pytest.mark.django_db
def test_contact_sender_with_ambiguous_org_dropped():
    from contacts.models import Contact
    from security.models import Organization
    org1 = Organization.objects.create(name="Org1", slug="org1", wazuh_group="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2", wazuh_group="org2")
    Contact.objects.create(organisation=org1, name="Alice", email="alice@shared.com")
    Contact.objects.create(organisation=org2, name="Alice", email="alice@shared.com")

    msg = _forwarded_msg(forwarder_email="alice@shared.com")
    result = PhishingIngestionHandler().handle(msg)
    assert result == "phishing:dropped:unknown_sender"


@pytest.mark.django_db
def test_user_lookup_takes_precedence_over_contact(acme, forwarder):
    from contacts.models import Contact
    from security.models import Organization
    other_org = Organization.objects.create(name="Other", slug="other", wazuh_group="other")
    Contact.objects.create(organisation=other_org, name="Carol", email="carol@acme.com")

    msg = _forwarded_msg(forwarder_email="carol@acme.com")
    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        PhishingIngestionHandler().handle(msg)

    alert = Alert.objects.get(source_kind="inbound_email")
    assert alert.organization == acme


# ── Auto-link forwarder contact (#387) ───────────────────────────────────────

@pytest.mark.django_db
def test_forwarder_contact_linked_on_created(acme, forwarder):
    from contacts.models import Contact, IncidentContact
    contact = Contact.objects.create(organisation=acme, name="Carol", email="carol@acme.com")
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:created"
    incident = Alert.objects.get(source_kind="inbound_email").incident
    assert IncidentContact.objects.filter(incident=incident, contact=contact).exists()


@pytest.mark.django_db
def test_forwarder_contact_linked_idempotent_on_dedup(acme, forwarder):
    from contacts.models import Contact, IncidentContact
    Contact.objects.create(organisation=acme, name="Carol", email="carol@acme.com")
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        PhishingIngestionHandler().handle(msg)
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:dedup"
    incident = Alert.objects.filter(source_kind="inbound_email").first().incident
    assert IncidentContact.objects.filter(incident=incident).count() == 1


@pytest.mark.django_db
def test_no_contact_record_no_error(acme, forwarder):
    from contacts.models import IncidentContact
    msg = _forwarded_msg()

    with patch("security.storage.StorageClient"), \
         patch("inbound_mail.handlers.get_system_user", return_value=forwarder):
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:created"
    assert IncidentContact.objects.count() == 0


# ── Phishing drop notification (#388) ─────────────────────────────────────────


@pytest.mark.django_db
def test_drop_notification_sent_to_known_contact_on_no_original_sender(acme):
    from contacts.models import Contact
    Contact.objects.create(organisation=acme, name="Carol", email="carol@acme.com")

    msg = NormalisedMessage(
        from_address="carol@acme.com",
        to_address="soc@vels.online",
        reply_to=None,
        subject="Fwd: Important",
        body_text="FYI\n---------- Forwarded message ---------\n",
        body_html="",
    )

    with patch("notifications.email.send_html_email") as mock_email:
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:dropped:no_original_sender"
    mock_email.assert_called_once()
    call_args = mock_email.call_args
    assert call_args[0][0] == "phishing_drop_notification"
    assert "carol@acme.com" in call_args[0][2]


@pytest.mark.django_db
def test_drop_notification_not_sent_when_contact_unknown(acme, forwarder):
    msg = NormalisedMessage(
        from_address="carol@acme.com",
        to_address="soc@vels.online",
        reply_to=None,
        subject="Fwd: Important",
        body_text="FYI\n---------- Forwarded message ---------\n",
        body_html="",
    )

    with patch("notifications.email.send_html_email") as mock_email:
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:dropped:no_original_sender"
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_drop_notification_not_sent_for_unknown_sender(acme):
    msg = _forwarded_msg(forwarder_email="stranger@unknown.com")

    with patch("notifications.email.send_html_email") as mock_email:
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:dropped:unknown_sender"
    mock_email.assert_not_called()


@pytest.mark.django_db
def test_drop_notification_not_sent_for_not_forward(acme, forwarder):
    from contacts.models import Contact
    Contact.objects.create(organisation=acme, name="Carol", email="carol@acme.com")

    msg = NormalisedMessage(
        from_address="carol@acme.com",
        to_address="soc@vels.online",
        reply_to=None,
        subject="Hello",
        body_text="Just a regular email.",
        body_html="",
    )

    with patch("notifications.email.send_html_email") as mock_email:
        outcome = PhishingIngestionHandler().handle(msg)

    assert outcome == "phishing:dropped:not_forward"
    mock_email.assert_not_called()
