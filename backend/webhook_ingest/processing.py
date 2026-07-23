"""The async processing pipeline shared by the worker task and Replay: turn a CapturedPayload
into records via the mapping engine + materialiser, recording one PayloadElementOutcome per
fanned-out element and the payload's aggregate status (CONTEXT.md → Captured Payload)."""

from django.utils import timezone

from . import mapping
from .materialise import materialise
from .models import CapturedPayload, PayloadElementOutcome

# Target types that create a new record each time (so retries/replays must be deduped by the
# idempotency key). Assets upsert on identity instead and are inherently convergent.
_CREATE_NEW_TARGETS = {"incident", "alert"}


def _seen_created(endpoint, key):
    """True if this endpoint already created a record for ``key`` — per-endpoint idempotency."""
    if not key:
        return False
    return PayloadElementOutcome.objects.filter(
        endpoint=endpoint, idempotency_key=key, outcome=PayloadElementOutcome.OUTCOME_CREATED
    ).exists()


def _record_outcome(payload, endpoint, index, key, outcome, error, obj, kind):
    fk = {"incident": None, "alert": None, "asset": None}
    if obj is not None and kind in fk:
        fk[kind] = obj
    PayloadElementOutcome.objects.update_or_create(
        captured_payload=payload,
        element_index=index,
        defaults={
            "endpoint": endpoint,
            "idempotency_key": key or "",
            "outcome": outcome,
            "error": error or "",
            "incident": fk["incident"],
            "alert": fk["alert"],
            "asset": fk["asset"],
        },
    )


def process_payload(payload):
    """Map + materialise every element of ``payload``, idempotently. Elements that already
    produced a record (a prior ``created`` outcome) are left untouched, so a Replay only works
    the unsatisfied ones. Returns the payload's new aggregate status."""
    endpoint = payload.endpoint
    config = mapping.config_from_endpoint(endpoint)

    already_created = {
        o.element_index
        for o in payload.outcomes.filter(outcome=PayloadElementOutcome.OUTCOME_CREATED)
    }

    resolved = mapping.resolve(config, payload.body, endpoint.target_type)

    if not resolved:
        payload.status = CapturedPayload.STATUS_FAILED
        payload.processed_at = timezone.now()
        payload.save(update_fields=["status", "processed_at"])
        return payload.status

    successes = 0
    for item in resolved:
        index = item["index"]
        key = item["idempotency_key"]
        if index in already_created:
            successes += 1
            continue

        if endpoint.target_type in _CREATE_NEW_TARGETS and _seen_created(endpoint, key):
            _record_outcome(
                payload, endpoint, index, key,
                PayloadElementOutcome.OUTCOME_SKIPPED, "duplicate idempotency key", None, None,
            )
            successes += 1
            continue

        obj, kind, error = materialise(endpoint, item["fields"])
        if obj is not None:
            _record_outcome(
                payload, endpoint, index, key,
                PayloadElementOutcome.OUTCOME_CREATED, "", obj, kind,
            )
            successes += 1
        else:
            _record_outcome(
                payload, endpoint, index, key,
                PayloadElementOutcome.OUTCOME_FAILED, error, None, kind,
            )

    total = len(resolved)
    if successes == total:
        payload.status = CapturedPayload.STATUS_CREATED
    elif successes == 0:
        payload.status = CapturedPayload.STATUS_FAILED
    else:
        payload.status = CapturedPayload.STATUS_PARTIAL
    payload.processed_at = timezone.now()
    payload.save(update_fields=["status", "processed_at"])
    return payload.status
