import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def process_captured_payload(payload_id):
    """Map + materialise a CapturedPayload once its endpoint is Active. A Capturing (or paused)
    endpoint leaves the payload pending — it is only a cached sample until a mapping goes live."""
    from .models import CapturedPayload, IngestEndpoint
    from .processing import process_payload

    try:
        payload = CapturedPayload.objects.select_related("endpoint").get(pk=payload_id)
    except CapturedPayload.DoesNotExist:
        return
    if payload.endpoint.state != IngestEndpoint.STATE_ACTIVE:
        return
    try:
        process_payload(payload)
    except Exception:
        logger.exception("process_captured_payload failed for %s", payload_id)


@shared_task
def purge_captured_payloads():
    """Delete Captured Payloads older than their endpoint's retention window so the cache stays
    bounded (CONTEXT.md → Captured Payload). Their element outcomes cascade with them."""
    from .models import CapturedPayload

    now = timezone.now()
    deleted = 0
    for payload in CapturedPayload.objects.select_related("endpoint").iterator():
        window = timedelta(days=payload.endpoint.retention_days or 30)
        if payload.received_at < now - window:
            payload.delete()
            deleted += 1
    return deleted
