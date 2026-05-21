import logging
import re

from django.core.signing import BadSignature, SignatureExpired

from contacts.tokens import unsign_contact_reply_token

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

        from contacts.models import Contact
        from incidents.models import Comment, Incident

        try:
            incident = Incident.objects.get(pk=incident_id)
            contact = Contact.objects.get(pk=contact_id)
        except (Incident.DoesNotExist, Contact.DoesNotExist):
            logger.warning("inbound_mail: incident %s or contact %s not found", incident_id, contact_id)
            return

        Comment.objects.create(
            incident=incident,
            body=message.body_text or message.subject,
            kind=Comment.KIND_SYSTEM,
            metadata={
                "source": "contact_reply",
                "contact_id": contact.id,
                "contact_name": contact.name,
            },
        )
        logger.info("inbound_mail: created comment on %s from contact %s", incident.display_id, contact.name)
