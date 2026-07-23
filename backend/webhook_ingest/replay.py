"""Replay for webhook Ingest Endpoints (CONTEXT.md → Captured Payload; ADR-0040). The webhook
sibling of ``partners/replay.py``.

`preview_endpoint` dry-runs the current mapping over the covered backlog without committing;
`replay_endpoint` re-runs Captured Payloads and their unsatisfied elements oldest-first,
skipping any element that already created a record. Two flows use it: onboarding the backlog
captured during the Capturing phase, and re-working failed/partial payloads after a mapping
edit."""

from . import mapping
from .models import CapturedPayload, PayloadElementOutcome
from .processing import process_payload

# Statuses whose payloads still have unsatisfied elements worth (re)running.
_REPLAYABLE = (
    CapturedPayload.STATUS_PENDING,
    CapturedPayload.STATUS_FAILED,
    CapturedPayload.STATUS_PARTIAL,
)


def _backlog(endpoint):
    return (
        CapturedPayload.objects.filter(endpoint=endpoint, status__in=_REPLAYABLE)
        .order_by("received_at")
    )


def preview_endpoint(endpoint):
    """Report what a Replay would do over the covered backlog, committing nothing: how many
    payloads and elements it would (re)attempt, and how many would resolve to no record."""
    config = mapping.config_from_endpoint(endpoint)
    payloads = list(_backlog(endpoint))
    would_attempt = 0
    empty_payloads = 0
    for payload in payloads:
        resolved = mapping.resolve(config, payload.body, endpoint.target_type)
        if not resolved:
            empty_payloads += 1
            continue
        created = {
            o.element_index
            for o in payload.outcomes.filter(outcome=PayloadElementOutcome.OUTCOME_CREATED)
        }
        would_attempt += sum(1 for item in resolved if item["index"] not in created)
    return {
        "payloads": len(payloads),
        "elements_to_attempt": would_attempt,
        "payloads_yielding_no_record": empty_payloads,
    }


def replay_endpoint(endpoint):
    """Re-run the covered backlog oldest-first. Idempotent: elements that already created a
    record are skipped. Returns per-payload result statuses."""
    results = []
    for payload in _backlog(endpoint):
        status = process_payload(payload)
        results.append({"captured_payload": payload.id, "status": status})
    return results
