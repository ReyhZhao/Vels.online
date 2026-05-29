import email
import imaplib
import logging
import os

from .dataclasses import NormalisedAttachment, NormalisedMessage

logger = logging.getLogger(__name__)

_REQUIRED_ENV = ("INBOUND_IMAP_HOST", "INBOUND_IMAP_USER", "INBOUND_IMAP_PASSWORD")


def _env_configured():
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def _extract_body(msg):
    """Return (body_text, body_html) from an email.message.Message."""
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_text:
                charset = part.get_content_charset() or "utf-8"
                body_text = part.get_payload(decode=True).decode(charset, errors="replace")
            elif ct == "text/html" and not body_html:
                charset = part.get_content_charset() or "utf-8"
                body_html = part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        ct = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True).decode(charset, errors="replace")
        if ct == "text/html":
            body_html = payload
        else:
            body_text = payload
    return body_text, body_html


def _extract_attachments(msg):
    """Return list of NormalisedAttachment for all non-body MIME parts."""
    attachments = []
    if not msg.is_multipart():
        return attachments
    body_content_types = {"text/plain", "text/html"}
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        ct = part.get_content_type()
        disposition = part.get_content_disposition() or ""
        if ct in body_content_types and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        filename = part.get_filename() or ""
        attachments.append(NormalisedAttachment(
            filename=filename,
            content_type=ct,
            payload=payload,
        ))
    return attachments


class ImapAdapter:
    def __init__(self):
        self._configured = _env_configured()
        if not self._configured:
            return
        self._host = os.environ["INBOUND_IMAP_HOST"]
        self._port = int(os.environ.get("INBOUND_IMAP_PORT", 993))
        self._user = os.environ["INBOUND_IMAP_USER"]
        self._password = os.environ["INBOUND_IMAP_PASSWORD"]
        self._mailbox = os.environ.get("INBOUND_IMAP_MAILBOX", "INBOX")

    def fetch_unseen(self):
        """Yield NormalisedMessage for each unseen message, marking each seen."""
        if not self._configured:
            return

        conn = imaplib.IMAP4_SSL(self._host, self._port)
        try:
            conn.login(self._user, self._password)
            conn.select(self._mailbox)
            _, data = conn.search(None, "UNSEEN")
            uids = data[0].split() if data[0] else []
            for uid in uids:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                body_text, body_html = _extract_body(msg)
                yield NormalisedMessage(
                    from_address=msg.get("From", ""),
                    to_address=msg.get("To", ""),
                    reply_to=msg.get("Reply-To"),
                    subject=msg.get("Subject", ""),
                    body_text=body_text,
                    body_html=body_html,
                    raw_bytes=raw,
                    attachments=_extract_attachments(msg),
                )
                conn.store(uid, "+FLAGS", "\\Seen")
        finally:
            try:
                conn.logout()
            except Exception:
                pass
