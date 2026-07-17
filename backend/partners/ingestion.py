"""Partner intake inbound path (ADR-0032).

A message whose From address belongs to an active Connection's sender set becomes a
Partner Incident directly (never an Alert, never correlated). Slotted into
inbound_mail.router BEFORE the phishing handler. Slice 2 always creates a new incident;
matching/threading (slice 4) and sender-auth verification (slice 3) layer on top.
"""

import email.utils
import hashlib
import io
import logging
import uuid

from django.utils import timezone

logger = logging.getLogger(__name__)


def _bare(address):
    _, addr = email.utils.parseaddr(address or "")
    return (addr or address or "").strip().lower()


def find_connection_for_sender(from_address):
    """Return (connection, sender_address) when from_address matches an *active*
    Connection's sender set, else (None, None). Used by the router to claim a message."""
    from partners.models import ConnectionSender

    addr = _bare(from_address)
    if not addr:
        return None, None
    sender = (
        ConnectionSender.objects.filter(address=addr)
        .select_related("connection", "connection__organization")
        .first()
    )
    if sender is None or not sender.connection.active:
        return None, None
    return sender.connection, addr


class PartnerIngestionHandler:
    def handle(self, message, connection, sender_address):
        """Ingest a claimed partner message. Returns an outcome string for stats.

        A message that fails DKIM/SPF verification is rejected and logged, never
        ingested (ADR-0032) — a spoofed From cannot inject incidents. Slice 2 otherwise
        always creates a new Partner Incident."""
        outcome, _ = ingest_partner_message(message, connection, sender_address)
        return outcome


def ingest_partner_message(message, connection, sender_address):
    """Core partner ingest, shared by the live router (via PartnerIngestionHandler) and
    Replay (ADR-0035). Returns `(outcome, incident_or_None)` — the incident is the one
    created or threaded onto, or None when verification failed."""
    from partners.mapping import map_email_to_incident_fields
    from partners.verification import verify_message_auth

    from partners.matching import find_partner_incident

    if not verify_message_auth(getattr(message, "raw_bytes", b"")):
        logger.warning(
            "inbound_mail: partner: dropped — sender-auth verification failed "
            "from=%r connection=%r subject=%r",
            sender_address, connection.name, message.subject,
        )
        return "partner:dropped:verification_failed", None

    fields = map_email_to_incident_fields(connection, message)
    ext_ref = fields.get("external_reference") or ""

    # Follow-up: a known reference threads onto the existing incident as a comment.
    # An inbound message NEVER mutates the incident's state (ADR-0032).
    existing = find_partner_incident(connection, ext_ref)
    if existing is not None:
        append_partner_comment(existing, message, connection, sender_address, ext_ref)
        logger.info(
            "inbound_mail: partner: matched follow-up onto %s connection=%r ref=%r",
            existing.display_id, connection.name, ext_ref,
        )
        return "partner:matched", existing

    incident = create_partner_incident(
        connection, message, fields, sender_address, flagged_no_reference=not ext_ref
    )
    logger.info(
        "inbound_mail: partner: created %s org=%s connection=%r sender=%r ref=%r",
        incident.display_id, connection.organization.slug, connection.name,
        sender_address, ext_ref,
    )
    return "partner:created", incident


def create_partner_incident(connection, message, fields, sender_address, flagged_no_reference=False):
    from django.db import transaction

    from incidents.models import Incident, Subject
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id

    subject = None
    if connection.kind == connection.KIND_VENDOR:
        subject, _ = Subject.objects.get_or_create(
            slug="vendor-advisory",
            defaults={"name": connection.VENDOR_ADVISORY_SUBJECT},
        )

    source_ref = {
        "connection_id": connection.id,
        "external_reference": fields.get("external_reference") or "",
        "sender_address": sender_address,
    }
    if flagged_no_reference:
        # A real report is never dropped for lack of a ref — open it, but flag it so
        # follow-ups can't thread onto it and staff can see it needs a reference.
        source_ref["flagged_no_reference"] = True
        logger.warning(
            "inbound_mail: partner: no External Reference — opening a flagged incident "
            "connection=%r sender=%r subject=%r",
            connection.name, sender_address, message.subject,
        )

    with transaction.atomic():
        incident = Incident.objects.create(
            organization=connection.organization,
            source_kind=Incident.SOURCE_PARTNER,
            source_ref=source_ref,
            display_id=next_display_id(),
            title=fields["title"],
            description=fields["description"],
            severity=fields["severity"],
            tlp=fields["tlp"],
            pap=fields["pap"],
            subject=subject,
        )
        record_event(
            incident,
            "partner_message_received",
            payload={
                "connection_id": connection.id,
                "connection_name": connection.name,
                "sender_address": sender_address,
                "external_reference": fields.get("external_reference") or "",
                "direction": "inbound",
            },
        )

    attach_partner_email(incident, message, sender_address)
    notify_partner_activity(incident, f"New partner incident {incident.display_id}")
    return incident


def append_partner_comment(incident, message, connection, sender_address, external_reference):
    """Thread a partner follow-up onto an existing incident as an external Comment.
    Never mutates the incident's state (ADR-0032)."""
    from incidents.models import Comment
    from incidents.services.events import record_event

    body = (message.body_text or message.subject or "").strip() or "(empty partner message)"
    Comment.objects.create(
        incident=incident,
        author=None,  # synthetic partner author — label carried in metadata
        body=body,
        kind=Comment.KIND_USER,
        origin=Comment.ORIGIN_PARTNER_INBOUND,
        is_internal=False,
        metadata={
            "partner_sender": sender_address,
            "connection_name": connection.name,
            "external_reference": external_reference,
        },
    )
    record_event(
        incident,
        "partner_message_received",
        payload={
            "connection_id": connection.id,
            "connection_name": connection.name,
            "sender_address": sender_address,
            "external_reference": external_reference,
            "direction": "inbound",
        },
    )
    attach_partner_email(incident, message, sender_address)
    notify_partner_activity(incident, f"Partner follow-up on {incident.display_id}")


def notify_partner_activity(incident, body):
    """Notify the incident's assignee (if any) of partner activity, and fire the normal
    high-severity org alert on creation."""
    from incidents.services.notifications_wiring import notify_incident_alert_if_needed

    if incident.assignee_id:
        try:
            from django.contrib.auth.models import User
            from notifications.services.notifications import notify

            assignee = User.objects.get(pk=incident.assignee_id)
            notify(
                "comment",
                [assignee],
                incident=incident,
                payload={
                    "title": f"Partner activity on {incident.display_id}",
                    "body": body[:200],
                    "link": f"/incidents/{incident.id}",
                },
            )
        except Exception:
            logger.exception("inbound_mail: partner: failed to notify assignee on %s", incident.display_id)

    notify_incident_alert_if_needed(incident)


def attach_partner_email(incident, message, sender_address):
    """Store the raw .eml and pass through any file attachments (mirrors the phishing
    handler's _attach_raw_email)."""
    from incidents.models import Attachment
    from security.storage import StorageClient
    from core import get_system_user

    storage = StorageClient()
    system_user = get_system_user()

    def _store(raw_bytes, filename, content_type):
        try:
            key = f"incidents/{incident.id}/{uuid.uuid4()}-{filename}"
            storage.upload_file(io.BytesIO(raw_bytes), key)
            Attachment.objects.create(
                incident=incident,
                uploader=system_user,
                s3_key=key,
                filename=filename,
                size_bytes=len(raw_bytes),
                content_type=content_type,
                sha256=hashlib.sha256(raw_bytes).hexdigest(),
                confirmed_at=timezone.now(),
            )
        except Exception:
            logger.exception(
                "inbound_mail: partner: failed to store attachment %r on %s",
                filename, incident.display_id,
            )

    if getattr(message, "raw_bytes", b""):
        _store(message.raw_bytes, f"partner-{sender_address}.eml", "message/rfc822")

    for att in getattr(message, "attachments", []) or []:
        if getattr(att, "payload", None):
            _store(att.payload, att.filename or "attachment", att.content_type or "application/octet-stream")
