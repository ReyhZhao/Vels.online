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
