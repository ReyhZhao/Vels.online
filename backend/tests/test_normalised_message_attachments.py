"""Tests for #315: NormalisedMessage raw_bytes/attachments and ImapAdapter."""
import email
import email.mime.multipart
import email.mime.text
import email.mime.base
from email import encoders
from unittest.mock import MagicMock, patch

import pytest

from inbound_mail.dataclasses import NormalisedAttachment, NormalisedMessage
from inbound_mail.adapters import ImapAdapter, _extract_attachments


# ── Dataclass structural tests ────────────────────────────────────────────────

def test_normalised_attachment_fields():
    att = NormalisedAttachment(filename="test.pdf", content_type="application/pdf", payload=b"data")
    assert att.filename == "test.pdf"
    assert att.content_type == "application/pdf"
    assert att.payload == b"data"


def test_normalised_message_defaults():
    msg = NormalisedMessage(
        from_address="a@b.com",
        to_address="c@d.com",
        reply_to=None,
        subject="Hi",
        body_text="text",
        body_html="",
    )
    assert msg.raw_bytes == b""
    assert msg.attachments == []


# ── _extract_attachments ──────────────────────────────────────────────────────

def _build_multipart_with_rfc822():
    outer = email.mime.multipart.MIMEMultipart()
    outer["From"] = "user@example.com"
    outer["To"] = "soc@vels.online"
    outer["Subject"] = "Fwd: phishing"

    body = email.mime.text.MIMEText("See attached.", "plain")
    outer.attach(body)

    inner = email.mime.text.MIMEText("Click here: http://evil.com", "plain")
    inner["From"] = "phisher@evil.com"
    inner["To"] = "victim@corp.com"
    inner["Subject"] = "Win a prize"

    attachment = email.mime.base.MIMEBase("message", "rfc822")
    attachment.set_payload([inner])
    attachment["Content-Disposition"] = "attachment"
    outer.attach(attachment)

    return outer


def test_extract_attachments_finds_rfc822():
    msg = _build_multipart_with_rfc822()
    attachments = _extract_attachments(msg)
    content_types = [a.content_type for a in attachments]
    assert "message/rfc822" in content_types


def test_extract_attachments_plain_message_returns_empty():
    msg = email.mime.text.MIMEText("Hello", "plain")
    attachments = _extract_attachments(msg)
    assert attachments == []


# ── ImapAdapter populates raw_bytes and attachments ───────────────────────────

def test_imap_adapter_populates_raw_bytes(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    monkeypatch.setenv("INBOUND_IMAP_PASSWORD", "pass")

    raw = _build_multipart_with_rfc822().as_bytes()
    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b"1"])
    mock_conn.fetch.return_value = (None, [(None, raw)])

    with patch("inbound_mail.adapters.imaplib.IMAP4_SSL", return_value=mock_conn):
        adapter = ImapAdapter()
        messages = list(adapter.fetch_unseen())

    assert len(messages) == 1
    assert messages[0].raw_bytes == raw


def test_imap_adapter_populates_attachments(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    monkeypatch.setenv("INBOUND_IMAP_PASSWORD", "pass")

    raw = _build_multipart_with_rfc822().as_bytes()
    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b"1"])
    mock_conn.fetch.return_value = (None, [(None, raw)])

    with patch("inbound_mail.adapters.imaplib.IMAP4_SSL", return_value=mock_conn):
        adapter = ImapAdapter()
        messages = list(adapter.fetch_unseen())

    att_types = [a.content_type for a in messages[0].attachments]
    assert "message/rfc822" in att_types


def test_imap_adapter_plain_message_empty_attachments(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    monkeypatch.setenv("INBOUND_IMAP_PASSWORD", "pass")

    raw = email.mime.text.MIMEText("Hello", "plain").as_bytes()
    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b"1"])
    mock_conn.fetch.return_value = (None, [(None, raw)])

    with patch("inbound_mail.adapters.imaplib.IMAP4_SSL", return_value=mock_conn):
        adapter = ImapAdapter()
        messages = list(adapter.fetch_unseen())

    assert messages[0].attachments == []
    assert messages[0].raw_bytes == raw
