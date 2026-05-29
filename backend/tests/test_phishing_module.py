"""Tests for #317: inbound_mail/phishing.py pure-function module."""
import email
import email.mime.multipart
import email.mime.text
import email.mime.base

import pytest

from inbound_mail.dataclasses import NormalisedAttachment, NormalisedMessage
from inbound_mail.phishing import (
    detect_forward,
    normalise_subject,
    extract_original_sender,
    resolve_org,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _msg(body_text="", attachments=None):
    return NormalisedMessage(
        from_address="user@corp.com",
        to_address="soc@vels.online",
        reply_to=None,
        subject="Fwd: phishing",
        body_text=body_text,
        body_html="",
        raw_bytes=b"",
        attachments=attachments or [],
    )


def _rfc822_attachment(inner_from="phisher@evil.com"):
    inner = email.mime.text.MIMEText("Click here: http://evil.com", "plain")
    inner["From"] = inner_from
    inner["To"] = "victim@corp.com"
    inner["Subject"] = "Win a prize"
    att_msg = email.mime.base.MIMEBase("message", "rfc822")
    att_msg.set_payload([inner])
    return NormalisedAttachment(
        filename="",
        content_type="message/rfc822",
        payload=inner.as_bytes(),
    )


# ── detect_forward ────────────────────────────────────────────────────────────

def test_detect_forward_rfc822_attachment():
    msg = _msg(attachments=[_rfc822_attachment()])
    assert detect_forward(msg) is True


def test_detect_forward_gmail_inline():
    body = "Hi,\n---------- Forwarded message ---------\nFrom: phisher@evil.com\n"
    msg = _msg(body_text=body)
    assert detect_forward(msg) is True


def test_detect_forward_outlook_inline():
    body = "See below.\n-----Original Message-----\nFrom: phisher@evil.com\n"
    msg = _msg(body_text=body)
    assert detect_forward(msg) is True


def test_detect_forward_plain_email():
    msg = _msg(body_text="Hello, just a regular email.")
    assert detect_forward(msg) is False


# ── normalise_subject ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Fwd: Win a prize", "win a prize"),
    ("Fw: Win a prize", "win a prize"),
    ("FW: Win a prize", "win a prize"),
    ("Re: Win a prize", "win a prize"),
    ("[EXT] Win a prize", "win a prize"),
    ("Fwd: Re: Win a prize", "win a prize"),
    ("Win a prize", "win a prize"),
    ("  Win a prize  ", "win a prize"),
])
def test_normalise_subject(raw, expected):
    assert normalise_subject(raw) == expected


# ── extract_original_sender ───────────────────────────────────────────────────

def test_extract_from_rfc822_attachment():
    att = _rfc822_attachment(inner_from="phisher@evil.com")
    msg = _msg(attachments=[att])
    result = extract_original_sender(msg, forwarder_address="user@corp.com")
    assert result == "phisher@evil.com"


def test_extract_from_gmail_inline():
    body = (
        "FYI see below.\n"
        "---------- Forwarded message ---------\n"
        "From: Phisher <phisher@evil.com>\n"
        "Subject: Win a prize\n"
    )
    msg = _msg(body_text=body)
    result = extract_original_sender(msg, forwarder_address="user@corp.com")
    assert result == "phisher@evil.com"


def test_extract_never_returns_forwarder():
    body = (
        "---------- Forwarded message ---------\n"
        "From: user@corp.com\n"
        "Subject: Win a prize\n"
    )
    msg = _msg(body_text=body)
    result = extract_original_sender(msg, forwarder_address="user@corp.com")
    assert result is None


def test_extract_never_returns_soc_address():
    body = (
        "---------- Forwarded message ---------\n"
        "From: soc@vels.online\n"
        "Subject: Win a prize\n"
    )
    msg = _msg(body_text=body)
    result = extract_original_sender(msg, forwarder_address="user@corp.com")
    assert result is None


def test_extract_returns_none_when_not_found():
    msg = _msg(body_text="No forwarding info here.")
    result = extract_original_sender(msg, forwarder_address="user@corp.com")
    assert result is None


# ── resolve_org ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_resolve_org_unknown_email():
    result = resolve_org("nobody@unknown.com")
    assert result is None


@pytest.mark.django_db
def test_resolve_org_via_default_org():
    from django.contrib.auth.models import User
    from security.models import Organization, OrganizationMembership
    from api.models import UserProfile

    org = Organization.objects.create(name="Corp", slug="corp", wazuh_group="corp")
    user = User.objects.create_user(username="alice", email="alice@corp.com", password="x")
    OrganizationMembership.objects.create(user=user, organization=org)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.default_org = org
    profile.save()

    result = resolve_org("alice@corp.com")
    assert result == org


@pytest.mark.django_db
def test_resolve_org_via_single_membership():
    from django.contrib.auth.models import User
    from security.models import Organization, OrganizationMembership

    org = Organization.objects.create(name="Solo", slug="solo", wazuh_group="solo")
    user = User.objects.create_user(username="bob", email="bob@solo.com", password="x")
    OrganizationMembership.objects.create(user=user, organization=org)

    result = resolve_org("bob@solo.com")
    assert result == org


@pytest.mark.django_db
def test_resolve_org_ambiguous_returns_none():
    from django.contrib.auth.models import User
    from security.models import Organization, OrganizationMembership

    org1 = Organization.objects.create(name="O1", slug="o1", wazuh_group="o1")
    org2 = Organization.objects.create(name="O2", slug="o2", wazuh_group="o2")
    user = User.objects.create_user(username="multi", email="multi@example.com", password="x")
    OrganizationMembership.objects.create(user=user, organization=org1)
    OrganizationMembership.objects.create(user=user, organization=org2)

    result = resolve_org("multi@example.com")
    assert result is None
