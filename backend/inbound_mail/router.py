import email.utils
import logging
import os

from .handlers import ContactReplyHandler, PhishingIngestionHandler, _extract_token
from partners.ingestion import PartnerIngestionHandler, find_connection_for_sender

logger = logging.getLogger(__name__)

_contact_handler = ContactReplyHandler()
_phishing_handler = PhishingIngestionHandler()
_partner_handler = PartnerIngestionHandler()


def _bare_soc_address():
    return os.environ.get("INBOUND_IMAP_USER", "")


def _parse_address(raw):
    """Return the bare email address from a possibly "Name <addr>" header value."""
    _, addr = email.utils.parseaddr(raw or "")
    return addr.lower() if addr else (raw or "").lower()


def route_inbound_message(message):
    """
    Route a NormalisedMessage to the appropriate handler.
    Returns an outcome string for stats tracking:
      "contact_reply", "partner:created",
      "phishing:created", "phishing:dedup",
      "phishing:dropped:<reason>", "dropped:unrecognised_to"
    """
    # Token extraction uses the raw To value — parseaddr mangles colon-delimited tokens.
    token = _extract_token(message.to_address)
    if token is not None:
        logger.debug(
            "inbound_mail: routing to ContactReplyHandler from=%r subject=%r",
            message.from_address, message.subject,
        )
        _contact_handler.handle(message)
        return "contact_reply"

    # Partner intake (ADR-0032): a message from a configured Connection sender becomes a
    # Partner Incident directly. Checked after the +token ContactReply path but BEFORE
    # the phishing handler. Loop-safe: our own outbound From is soc@, which matches no
    # Connection sender.
    connection, sender_address = find_connection_for_sender(message.from_address)
    if connection is not None:
        logger.debug(
            "inbound_mail: routing to PartnerIngestionHandler from=%r connection=%r subject=%r",
            message.from_address, connection.name, message.subject,
        )
        return _capture_intake(message, _partner_handler.handle(message, connection, sender_address))

    # For bare-address comparison, parse out any display name ("SOC <soc@vels.online>").
    bare_soc = _bare_soc_address().lower()
    to_parsed = _parse_address(message.to_address)
    if bare_soc and to_parsed == bare_soc:
        logger.debug(
            "inbound_mail: routing to PhishingIngestionHandler from=%r subject=%r",
            message.from_address, message.subject,
        )
        return _capture_intake(message, _phishing_handler.handle(message))

    logger.warning(
        "inbound_mail: unrecognised To address — from=%r to=%r to_parsed=%r subject=%r bare_soc=%r",
        message.from_address, message.to_address, to_parsed, message.subject, bare_soc,
    )
    return _capture_intake(message, "dropped:unrecognised_to")


def _capture_intake(message, outcome):
    """Land every terminal-drop outcome in the staff Intake Inbox (ADR-0032)."""
    from partners.intake import is_terminal_drop, record_intake_drop

    if is_terminal_drop(outcome):
        record_intake_drop(message, outcome)
    return outcome
