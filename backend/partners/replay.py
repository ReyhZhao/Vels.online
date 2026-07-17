"""Intake Inbox Replay (ADR-0035 / CONTEXT.md → Replay).

Once a Connection covers a sender, its held Intake Inbox backlog can be *replayed* — each
retained raw `.eml` fed straight back through the live partner pipeline
(`ingest_partner_message`) so the missed Incident is created and held follow-ups thread
onto it. Replay reuses the live path verbatim: the same DKIM/SPF gate, field-mapping and
`(connection, External Reference)` matching. There is no trusted-replay bypass — a message
that cannot pass re-verification stays dead-lettered.

Replay is Connection-scoped, oldest-first (so a create precedes its updates), and
idempotent per row (`replayed_at`/`replayed_incident` mark done rows; a mid-batch failure
resumes rather than double-ingesting).
"""

import logging
from functools import reduce
from operator import or_

from django.db.models import Q

logger = logging.getLogger(__name__)


def _connection_sender_addresses(connection):
    """Lowercased sender addresses configured on the Connection."""
    return [s.address.strip().lower() for s in connection.senders.all() if s.address]


def covered_backlog(connection):
    """Held Intake Inbox rows eligible for replay under this Connection, oldest-first:
    sender in the Connection's sender set (case-insensitive), a retained raw `.eml`, and
    not already replayed. Shared by the preview (GET) and the actual replay (POST) so both
    agree on what will happen."""
    from partners.models import IntakeInboxMessage

    addresses = _connection_sender_addresses(connection)
    if not addresses:
        return IntakeInboxMessage.objects.none()
    sender_q = reduce(or_, (Q(sender__iexact=a) for a in addresses))
    return (
        IntakeInboxMessage.objects.filter(sender_q)
        .filter(replayed_at__isnull=True)
        .exclude(raw_s3_key="")
        .order_by("received_at")
    )


def _load_raw(row):
    """Fetch the retained raw `.eml` bytes for a row, or None if it can't be read."""
    try:
        from security.storage import StorageClient

        return StorageClient().get_bytes(row.raw_s3_key)
    except Exception:
        logger.exception("partner: replay could not read raw object %r for row %s", row.raw_s3_key, row.pk)
        return None


def _delete_raw(row):
    """Best-effort delete of a row's retained raw object after a successful replay — the
    bytes now live as an attachment on the created/threaded incident."""
    try:
        from security.storage import StorageClient

        StorageClient().delete_file(row.raw_s3_key)
    except Exception:
        logger.exception("partner: replay could not delete raw object %r for row %s", row.raw_s3_key, row.pk)


def preview_connection_backlog(connection):
    """Dry-run what a replay would do, without mutating anything (ADR-0035 / #715).

    Uses the *same* gathering + mapping as the actual replay, so preview and POST agree.
    For each covered held row it reconstructs the message and extracts the External
    Reference the mapping would use, so staff can see whether the backlog threads into one
    incident or fragments into several flagged ones *before* committing. Returns
    {count, without_reference, messages:[{id, sender, subject, received_at,
    external_reference, has_reference}]}."""
    from inbound_mail.adapters import message_from_bytes
    from partners.mapping import extract_external_reference

    messages = []
    without_reference = 0
    for row in covered_backlog(connection):
        raw = _load_raw(row)
        if raw is None:
            # Unreadable object won't be replayed either — omit so preview matches POST.
            continue
        message = message_from_bytes(raw)
        ext_ref = extract_external_reference(connection, message)
        if not ext_ref:
            without_reference += 1
        messages.append({
            "id": row.id,
            "sender": row.sender,
            "subject": row.subject,
            "received_at": row.received_at.isoformat() if row.received_at else None,
            "external_reference": ext_ref,
            "has_reference": bool(ext_ref),
        })
    return {
        "count": len(messages),
        "without_reference": without_reference,
        "messages": messages,
    }


def replay_connection_backlog(connection):
    """Replay the Connection's held backlog oldest-first through the live pipeline.

    Returns a list of per-message outcomes: {id, outcome: created|matched|
    verification_failed, incident_id?, incident_display_id?}. Rows are locked with
    `select_for_update(skip_locked=True)` so a concurrent run can't double-ingest, and each
    successful ingest marks the row and drops its retained raw."""
    from django.db import transaction
    from django.utils import timezone

    from inbound_mail.adapters import message_from_bytes
    from partners.ingestion import ingest_partner_message

    results = []
    with transaction.atomic():
        rows = list(covered_backlog(connection).select_for_update(skip_locked=True))
        for row in rows:
            raw = _load_raw(row)
            if raw is None:
                # Object gone (e.g. purged mid-run) — leave the row, nothing to replay.
                continue
            message = message_from_bytes(raw)
            # Re-verification uses the *retained* raw's Authentication-Results; a message
            # that never carried a passing header stays dead-lettered and unmarked.
            outcome, incident = ingest_partner_message(message, connection, row.sender)
            if incident is None:
                results.append({"id": row.id, "outcome": "verification_failed"})
                continue

            _delete_raw(row)
            row.replayed_at = timezone.now()
            row.replayed_incident = incident
            row.raw_s3_key = ""
            row.save(update_fields=["replayed_at", "replayed_incident", "raw_s3_key"])
            results.append({
                "id": row.id,
                "outcome": "created" if outcome == "partner:created" else "matched",
                "incident_id": incident.id,
                "incident_display_id": incident.display_id,
            })

    logger.info(
        "partner: replayed backlog for connection=%r (%d message(s))",
        connection.name, len(results),
    )
    return results
