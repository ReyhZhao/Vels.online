"""Suggestion reconciler — the Detection Scan's Firing-analog dedup ledger (ADR-0036).

``reconcile(org, proposed_ids)`` decides create / fold-into-pending / suppress
purely from the org's existing DetectionSuggestion rows (no dedup model of its
own), mirroring the static engine's "one live per key / re-fire only after
closure":

- at most one *live* (pending) Suggestion per grouping — a substantially
  overlapping proposal folds into the live row instead of spawning a second;
- a *dismissed* Suggestion suppresses re-proposal of the same or a subset set;
- a *materially larger* set than a dismissed one (new evidence) re-proposes;
- accepted alerts become ``imported`` and leave the Residual pool naturally,
  so accepted rows need no rule here.
"""
from dataclasses import dataclass
from typing import Optional

ACTION_CREATE = "create"
ACTION_FOLD = "fold"
ACTION_SUPPRESS = "suppress"

# A dismissed grouping re-proposes only when materially larger: at least this
# many alerts beyond the dismissed set — genuine new evidence, not one stray.
MATERIAL_NEW_ALERTS = 2

# A pending Suggestion absorbs a proposal when they substantially overlap:
# shared alerts ≥ this fraction of the smaller of the two sets.
FOLD_OVERLAP_FRACTION = 0.5


@dataclass
class ReconcileDecision:
    action: str
    suggestion: Optional[object] = None  # the pending row to fold into (ACTION_FOLD only)


def reconcile(org, proposed_ids) -> ReconcileDecision:
    from correlations.models import DetectionSuggestion

    proposed = set(proposed_ids)

    rows = DetectionSuggestion.objects.filter(
        organization=org,
        status__in=[DetectionSuggestion.STATUS_PENDING, DetectionSuggestion.STATUS_DISMISSED],
    ).prefetch_related("proposed_alerts")

    pending, dismissed = [], []
    for row in rows:
        ids = {a.id for a in row.proposed_alerts.all()}
        if row.status == DetectionSuggestion.STATUS_PENDING:
            pending.append((row, ids))
        else:
            dismissed.append((row, ids))

    # Dismissal suppresses first: the analyst already called this noise. Only a
    # materially larger set — new evidence — may bring the grouping back.
    for _row, ids in dismissed:
        if proposed <= ids:
            return ReconcileDecision(ACTION_SUPPRESS)
        if proposed & ids and len(proposed - ids) < MATERIAL_NEW_ALERTS:
            return ReconcileDecision(ACTION_SUPPRESS)

    # One live pending per grouping.
    for row, ids in pending:
        if proposed <= ids:
            return ReconcileDecision(ACTION_SUPPRESS)
        overlap = len(proposed & ids)
        if overlap and overlap / min(len(proposed), len(ids)) >= FOLD_OVERLAP_FRACTION:
            return ReconcileDecision(ACTION_FOLD, suggestion=row)

    return ReconcileDecision(ACTION_CREATE)
