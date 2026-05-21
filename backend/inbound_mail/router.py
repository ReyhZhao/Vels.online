import logging

from .handlers import ContactReplyHandler, _extract_token

logger = logging.getLogger(__name__)

_handler = ContactReplyHandler()


def route_inbound_message(message):
    """Route a single NormalisedMessage to the appropriate handler."""
    token = _extract_token(message.to_address)
    if token is None:
        logger.info("inbound_mail: no + suffix in To %r — dropping", message.to_address)
        return
    _handler.handle(message)
