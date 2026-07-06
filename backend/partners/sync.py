"""Bi-directional partner sync (ADR-0033).

Mirror our staff-authored external comments and our closure to the partner over email,
so the incident thread *is* the conversation. `should_sync_to_partner` is the single
gate: bidirectional Connection + staff-authored external comment, with loop-prevention
(partner-inbound / AI comments never echo) and a TLP:RED kill switch.

Outbound `From` is the SOC mailbox (soc@), which matches no Connection sender, so our own
mail is never re-ingested. The outbound `Subject` carries the External Reference so the
partner re-threads.
"""

import logging
import os

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def get_partner_connection(incident):
    """Return the Connection a partner incident originated from, or None."""
    from incidents.models import Incident
    from partners.models import Connection

    if incident.source_kind != Incident.SOURCE_PARTNER:
        return None
    cid = (incident.source_ref or {}).get("connection_id")
    if not cid:
        return None
    return Connection.objects.filter(pk=cid).prefetch_related("senders").first()


def should_sync_to_partner(comment):
    """Does this comment mirror to the partner? (ADR-0033)

    True only when: the incident came from a **bidirectional** Connection; the comment is
    a **staff-authored** external user comment (`kind=user`, `origin=staff`,
    `is_internal=False`); and the incident is **not TLP:RED**. Partner-inbound and
    AI-origin comments never echo (loop-prevention); internal comments never leave;
    TLP:RED suppresses all outbound."""
    from incidents.models import Comment

    incident = comment.incident
    if comment.is_internal:
        return False
    if comment.kind != Comment.KIND_USER or comment.origin != Comment.ORIGIN_STAFF:
        return False
    if incident.tlp == incident.TLP_RED:
        return False
    connection = get_partner_connection(incident)
    if connection is None or connection.direction != connection.DIRECTION_BIDIRECTIONAL:
        return False
    return True


def sync_comment_to_partner(comment):
    """Mirror a staff-authored external comment to the partner. Returns True if sent."""
    if not should_sync_to_partner(comment):
        return False
    incident = comment.incident
    connection = get_partner_connection(incident)
    if not _send_partner_email(incident, connection, comment.body):
        return False
    _record_outbound(incident, connection, f"Comment mirrored to partner ({connection.name}).")
    return True


def sync_closure_to_partner(incident):
    """Auto-notify the partner that we closed our side. Returns True if sent.

    Gated identically to comments: bidirectional Connection + not TLP:RED."""
    connection = get_partner_connection(incident)
    if connection is None or connection.direction != connection.DIRECTION_BIDIRECTIONAL:
        return False
    if incident.tlp == incident.TLP_RED:
        return False
    body = f"We have closed our side of this case (reason: {incident.closure_reason})."
    if not _send_partner_email(incident, connection, body):
        return False
    _record_outbound(incident, connection, "Closure notified to partner.")
    return True


def _soc_from_address():
    return os.environ.get("INBOUND_IMAP_USER") or settings.DEFAULT_FROM_EMAIL


def _outbound_subject(incident):
    ref = (incident.source_ref or {}).get("external_reference") or ""
    prefix = f"[{ref}] " if ref else ""
    return f"{prefix}{incident.display_id}: {incident.title}"


def _send_partner_email(incident, connection, body):
    recipients = list(connection.senders.values_list("address", flat=True))
    if not recipients:
        logger.warning("partner: no recipient addresses for connection %r", connection.name)
        return False
    try:
        EmailMessage(
            subject=_outbound_subject(incident),
            body=body,
            from_email=_soc_from_address(),
            to=recipients,
        ).send()
    except Exception:
        logger.exception("partner: failed to send outbound email for %s", incident.display_id)
        return False
    return True


def _record_outbound(incident, connection, summary):
    """Record the send as an internal system Comment + a partner_message_sent event.

    The record Comment is `kind=system`/`is_internal=True`, so it never re-triggers the
    sync gate (which requires a staff user external comment)."""
    from incidents.models import Comment
    from incidents.services.events import record_event

    Comment.objects.create(
        incident=incident,
        author=None,
        body=summary,
        kind=Comment.KIND_SYSTEM,
        is_internal=True,
        metadata={"partner_outbound": True, "connection_name": connection.name},
    )
    record_event(
        incident,
        "partner_message_sent",
        payload={
            "connection_id": connection.id,
            "connection_name": connection.name,
            "direction": "outbound",
            "summary": summary,
        },
    )
