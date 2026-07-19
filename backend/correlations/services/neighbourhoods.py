"""Candidate Neighbourhood assembler for the Detection Scan (PRD #727, ADR-0036).

Pure function of DB + clock: for each Residual alert (`new`/unlinked, settled,
within lookback) gather the org's alerts sharing *any* ECS entity value within
the window (v1 = union) from the indexed `AlertEntity` table. Each neighbourhood
splits into Residual (proposable) and already-handled (read-only context) alerts.

Org-scoped join is a hard invariant: the AlertEntity lookup is unconditionally
filtered to the organisation, so a common entity value (`administrator`,
`8.8.8.8`) never bridges tenants.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

# Residual definition (CONTEXT.md): aged past the settle delay, within lookback.
SETTLE_MINUTES = 15
LOOKBACK_HOURS = 24

# Hard size cap per neighbourhood — a safety valve against the noisy-host union
# balloon and the direct token-budget lever (ADR-0036), not a tuning knob.
NEIGHBOURHOOD_SIZE_CAP = 25


@dataclass
class Neighbourhood:
    """One Candidate Neighbourhood: what the LLM may propose vs. read-only context."""

    residual_alerts: list = field(default_factory=list)
    context_alerts: list = field(default_factory=list)

    @property
    def alerts(self):
        return self.residual_alerts + self.context_alerts


def assemble_neighbourhoods(org, now=None):
    """Assemble union Candidate Neighbourhoods for one organisation.

    Deterministic: residual alerts are visited oldest-first; a residual alert
    already covered by an earlier neighbourhood's residual set does not anchor
    its own. Neighbourhoods with fewer than 2 alerts are dropped (no valid
    proposal can come from a single alert).
    """
    from alerts.models import Alert, AlertEntity

    now = now or timezone.now()
    settle_cutoff = now - timedelta(minutes=SETTLE_MINUTES)
    lookback_cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    residuals = list(
        Alert.objects.filter(
            organization=org,
            state="new",
            incident__isnull=True,
            created_at__gte=lookback_cutoff,
            created_at__lte=settle_cutoff,
        )
        .order_by("created_at")
        .prefetch_related("entities")
    )
    if not residuals:
        return []

    residual_ids = {a.id for a in residuals}

    neighbourhoods = []
    covered = set()
    for anchor in residuals:
        if anchor.id in covered:
            continue

        entity_pairs = {(e.entity_type, e.value) for e in anchor.entities.all()}
        neighbour_ids = {anchor.id}
        if entity_pairs:
            entity_q = Q()
            for entity_type, value in entity_pairs:
                entity_q |= Q(entity_type=entity_type, value=value)
            neighbour_ids |= set(
                AlertEntity.objects.filter(organization=org)  # hard org-scope invariant
                .filter(entity_q)
                .filter(alert__created_at__gte=lookback_cutoff)
                .values_list("alert_id", flat=True)
            )

        # Newest-first so the size cap keeps the freshest evidence.
        alerts = list(
            Alert.objects.filter(organization=org, id__in=neighbour_ids)
            .order_by("-created_at")
            .prefetch_related("entities")
        )
        residual_part = [a for a in alerts if a.id in residual_ids]
        context_part = [a for a in alerts if a.id not in residual_ids]

        if len(residual_part) > NEIGHBOURHOOD_SIZE_CAP:
            # Never cap out the anchor — it is the reason this neighbourhood exists.
            kept = residual_part[: NEIGHBOURHOOD_SIZE_CAP]
            if anchor.id not in {a.id for a in kept}:
                kept[-1] = anchor
            residual_part = kept
        context_part = context_part[: max(0, NEIGHBOURHOOD_SIZE_CAP - len(residual_part))]

        covered.update(a.id for a in residual_part)

        if len(residual_part) + len(context_part) < 2:
            continue
        neighbourhoods.append(
            Neighbourhood(residual_alerts=residual_part, context_alerts=context_part)
        )

    return neighbourhoods
