"""Supersede simpler (fast-path) incidents when a correlation rule fires."""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)

_ACTIVE_WORK_STATES = frozenset({"in_progress", "on_hold"})


def supersede_simpler_incidents(chain_incident, prior_incidents, rule):
    """Absorb simpler (fast-path) incidents into the chain incident.

    For each candidate incident:
    - Guard rail: if it is in_progress/on_hold or has an assignee, flag for human
      confirmation instead of auto-superseding.
    - Otherwise: relink all its alerts to chain_incident, mark it duplicate_of the
      chain incident, and close it CLOSURE_DUPLICATE.

    Must be called inside an existing transaction.atomic() block.
    """
    from alerts.models import Alert
    from incidents.models import Incident
    from incidents.services.events import record_event

    seen = set()
    for simpler in prior_incidents:
        if simpler.pk in seen or simpler.pk == chain_incident.pk:
            continue
        seen.add(simpler.pk)

        if simpler.source_kind == Incident.SOURCE_CORRELATION:
            continue

        if simpler.state in _ACTIVE_WORK_STATES or simpler.assignee_id is not None:
            logger.info(
                "supersede: skipping %s (state=%s, assigned=%s) — flagging for human confirmation",
                simpler.display_id,
                simpler.state,
                bool(simpler.assignee_id),
            )
            record_event(
                chain_incident,
                "supersede_blocked",
                payload={
                    "blocked_incident_id": simpler.id,
                    "blocked_incident_display_id": simpler.display_id,
                    "reason": "active_work",
                    "state": simpler.state,
                    "assigned": bool(simpler.assignee_id),
                    "rule_name": rule.name,
                },
            )
            continue

        Alert.objects.filter(incident=simpler).update(incident=chain_incident)

        simpler.state = Incident.STATE_CLOSED
        simpler.closure_reason = Incident.CLOSURE_DUPLICATE
        simpler.duplicate_of = chain_incident
        simpler.save(update_fields=["state", "closure_reason", "duplicate_of", "updated_at"])

        record_event(
            simpler,
            "superseded",
            payload={
                "chain_incident_id": chain_incident.id,
                "chain_incident_display_id": chain_incident.display_id,
                "rule_id": rule.id,
                "rule_name": rule.name,
            },
        )
        record_event(
            chain_incident,
            "absorbed_incident",
            payload={
                "absorbed_incident_id": simpler.id,
                "absorbed_incident_display_id": simpler.display_id,
                "rule_id": rule.id,
                "rule_name": rule.name,
            },
        )
        logger.info(
            "supersede: absorbed %s into %s (rule=%s)",
            simpler.display_id,
            chain_incident.display_id,
            rule.name,
        )
