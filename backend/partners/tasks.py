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
    inbound spam/phishing bodies don't accumulate indefinitely (ADR-0032)."""
    from partners.models import IntakeInboxMessage

    try:
        days = int(os.environ.get("PARTNER_INTAKE_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = IntakeInboxMessage.objects.filter(received_at__lt=cutoff).delete()
    logger.info("purge_intake_inbox: deleted %d Intake Inbox row(s) older than %d days", deleted, days)
    return deleted
