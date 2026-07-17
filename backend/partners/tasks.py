import logging
import os
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


@shared_task
def purge_intake_inbox():
    """Delete Intake Inbox rows older than PARTNER_INTAKE_RETENTION_DAYS (default 30) so
    inbound spam/phishing bodies don't accumulate indefinitely (ADR-0032). The retained
    raw `.eml` object shares this single window and is deleted *before* its row so no raw
    payload outlives its metadata (ADR-0035)."""
    from partners.models import IntakeInboxMessage

    try:
        days = int(os.environ.get("PARTNER_INTAKE_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)

    storage = None
    deleted = 0
    for row in IntakeInboxMessage.objects.filter(received_at__lt=cutoff).iterator():
        if row.raw_s3_key:
            try:
                from security.storage import StorageClient

                if storage is None:
                    storage = StorageClient()
                storage.delete_file(row.raw_s3_key)
            except Exception:
                # Best-effort: a missing/already-deleted object must not strand the row.
                logger.exception(
                    "purge_intake_inbox: failed to delete raw object %r for row %s",
                    row.raw_s3_key, row.pk,
                )
        row.delete()
        deleted += 1

    logger.info("purge_intake_inbox: deleted %d Intake Inbox row(s) older than %d days", deleted, days)
    return deleted
