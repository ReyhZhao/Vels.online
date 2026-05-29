import logging
import os

from .handlers import ContactReplyHandler, PhishingIngestionHandler, _extract_token

logger = logging.getLogger(__name__)

_contact_handler = ContactReplyHandler()
_phishing_handler = PhishingIngestionHandler()


def _bare_soc_address():
    return os.environ.get("INBOUND_IMAP_USER", "")


def route_inbound_message(message):
    """Route a single NormalisedMessage to the appropriate handler."""
    token = _extract_token(message.to_address)
    if token is not None:
        _contact_handler.handle(message)
        return

    bare_soc = _bare_soc_address()
    if bare_soc and message.to_address and message.to_address.lower() == bare_soc.lower():
        _phishing_handler.handle(message)
        return

    logger.info("inbound_mail: unrecognised To %r — dropping", message.to_address)
