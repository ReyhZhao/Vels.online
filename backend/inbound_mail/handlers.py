import hashlib
import io
import logging
import os
import re
import uuid

from django.core.signing import BadSignature, SignatureExpired
from django.utils import timezone

from contacts.tokens import unsign_contact_reply_token
from core import get_system_user
from security.storage import StorageClient

logger = logging.getLogger(__name__)

_PLUS_RE = re.compile(r"[^@+]+\+([^@]+)@")


def _extract_token(address):
    """Return the +suffix token from an email address, or None."""
    m = _PLUS_RE.search(address or "")
    return m.group(1) if m else None


class ContactReplyHandler:
    def handle(self, message):
        token = _extract_token(message.to_address)
        if not token:
            logger.warning("inbound_mail: no + token in To address %r", message.to_address)
            return

        try:
            incident_id, contact_id = unsign_contact_reply_token(token)
        except SignatureExpired:
            logger.warning("inbound_mail: expired token in To address %r", message.to_address)
            return
        except (BadSignature, Exception):
            logger.warning("inbound_mail: invalid token in To address %r", message.to_address)
            return

        from contacts.models import Contact, ContactMessage
        from incidents.models import Incident

        try:
            incident = Incident.objects.get(pk=incident_id)
            contact = Contact.objects.get(pk=contact_id)
        except (Incident.DoesNotExist, Contact.DoesNotExist):
            logger.warning("inbound_mail: incident %s or contact %s not found", incident_id, contact_id)
            return

        parent = (
            ContactMessage.objects.filter(
                incident=incident,
                contact=contact,
                direction=ContactMessage.DIRECTION_OUTBOUND,
            )
            .order_by("-created_at")
            .first()
        )

        ContactMessage.objects.create(
            incident=incident,
            contact=contact,
            direction=ContactMessage.DIRECTION_INBOUND,
            body=message.body_text or message.subject,
            parent=parent,
        )
        logger.info("inbound_mail: created contact message on %s from contact %s", incident.display_id, contact.name)

        from incidents.services.events import record_event
        record_event(incident, "contact_message_received", payload={
            "contact_id": contact.id,
            "contact_name": contact.name,
        })


class PhishingIngestionHandler:
    def handle(self, message):
        from .phishing import detect_forward, resolve_org, normalise_subject, extract_original_sender

        if not detect_forward(message):
            logger.info("inbound_mail: phishing: not a forwarded email — dropping")
            return

        org = resolve_org(message.from_address)
        if org is None:
            logger.info(
                "inbound_mail: phishing: unknown or ambiguous sender %r — dropping",
                message.from_address,
            )
            return

        forwarder_address = message.from_address
        sender_address = extract_original_sender(message, forwarder_address)
        if sender_address is None:
            logger.info("inbound_mail: phishing: could not extract original sender — dropping")
            return

        subject_normalised = normalise_subject(message.subject)
        source_ref = {
            "sender_address": sender_address,
            "subject_normalised": subject_normalised,
            "forwarder_address": forwarder_address,
        }

        from alerts.models import Alert
        from alerts.services.identifiers import next_alert_display_id
        from alerts.services.routing import route_alert

        alert = Alert.objects.create(
            organization=org,
            source_kind="inbound_email",
            severity="high",
            source_ref=source_ref,
            title=f"Phishing: {subject_normalised or sender_address}",
            display_id=next_alert_display_id(),
        )
        route_alert(alert)
        alert.refresh_from_db()

        incident = alert.incident
        if incident and message.raw_bytes:
            self._attach_raw_email(incident, message.raw_bytes, sender_address)

    def _attach_raw_email(self, incident, raw_bytes, sender_address):
        try:
            from incidents.models import Attachment

            filename = f"phishing-{sender_address}.eml"
            key = f"incidents/{incident.id}/{uuid.uuid4()}-{filename}"
            sha256 = hashlib.sha256(raw_bytes).hexdigest()

            StorageClient().upload_file(io.BytesIO(raw_bytes), key)

            Attachment.objects.create(
                incident=incident,
                uploader=get_system_user(),
                s3_key=key,
                filename=filename,
                size_bytes=len(raw_bytes),
                content_type="message/rfc822",
                sha256=sha256,
                confirmed_at=timezone.now(),
            )
        except Exception:
            logger.exception("inbound_mail: phishing: failed to attach raw email to incident %s", incident.display_id)
