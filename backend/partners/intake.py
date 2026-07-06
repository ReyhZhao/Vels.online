"""Intake Inbox capture (ADR-0032 / CONTEXT.md → Intake Inbox).

The inbound_mail router funnels every terminal-drop outcome through
`record_intake_drop`, which lands a bounded metadata row in the Intake Inbox so staff can
see who is emailing the SOC mailbox and bouncing, and onboard a Connection from it.
"""

import email.utils
import logging

logger = logging.getLogger(__name__)

BODY_EXCERPT_LIMIT = 500


def is_terminal_drop(outcome):
    """A router outcome that means the message was NOT handled (no incident/alert/reply)."""
    return bool(outcome) and (outcome.startswith("dropped:") or ":dropped:" in outcome)


def record_intake_drop(message, drop_reason):
    """Persist a dropped inbound message as an Intake Inbox row. Best-effort — never
    raises into the router."""
    from partners.models import IntakeInboxMessage

    try:
        _, sender = email.utils.parseaddr(message.from_address or "")
        IntakeInboxMessage.objects.create(
            sender=(sender or message.from_address or "")[:320],
            subject=(message.subject or "")[:500],
            drop_reason=(drop_reason or "")[:100],
            body_excerpt=(message.body_text or "")[:BODY_EXCERPT_LIMIT],
        )
    except Exception:
        logger.exception("partner: failed to record Intake Inbox drop (%s)", drop_reason)
