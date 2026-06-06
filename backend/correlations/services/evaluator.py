import json
import logging
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone

from correlations.services.matching import alert_matches_leg

logger = logging.getLogger(__name__)

_CLOSED_STATE = "closed"


def _correlation_key_value(alert, correlation_key):
    """Return the correlation key value for the alert, or None if the entity is absent."""
    if correlation_key == "none":
        return "none"
    entity = alert.entities.filter(entity_type=correlation_key).first()
    return entity.value if entity else None


def _get_window_alerts(org, correlation_key, key_value, window_start):
    """Return all alerts in the rolling window for this org and correlation key value."""
    from alerts.models import Alert

    qs = Alert.objects.filter(
        organization=org,
        created_at__gte=window_start,
    ).select_related("incident").prefetch_related("entities")

    if correlation_key != "none":
        qs = qs.filter(entities__entity_type=correlation_key, entities__value=key_value).distinct()

    return list(qs)


def _link_alert_to_incident(alert, incident, rule):
    from incidents.services.events import record_event

    if alert.incident_id == incident.id:
        return

    alert.state = "imported"
    alert.incident = incident
    alert.save(update_fields=["state", "incident", "updated_at"])

    record_event(
        incident,
        "alert_linked",
        payload={
            "alert_display_id": alert.display_id,
            "source": "correlation_rule",
            "rule_name": rule.name,
        },
    )


def _compose_description(rule, key_value, matching_alerts):
    """Build a human-readable incident description from the contributing alerts.

    Includes the rule name, the correlation key/value, and per-alert detail
    (identifier, title, severity, source kind, entities, and the alert's raw
    source data) so staff and the auto-triage pipeline have real context and so
    IOC extraction — which reads the incident's title + description — has the
    alerts' raw content to extract from.
    """
    alerts = sorted(matching_alerts, key=lambda a: (a.created_at, a.display_id or ""))

    lines = [
        f"Correlation rule **{rule.name}** fired.",
        f"Correlation key: {rule.correlation_key} = {key_value}",
        "",
        f"## Contributing alerts ({len(alerts)})",
        "",
    ]

    for alert in alerts:
        entities = ", ".join(
            f"{e.entity_type}={e.value}" for e in alert.entities.all()
        ) or "—"
        lines.append(f"### {alert.display_id}: {alert.title or '(untitled)'}")
        lines.append(f"- Severity: {alert.severity or '—'}")
        lines.append(f"- Source kind: {alert.source_kind}")
        lines.append(f"- Entities: {entities}")
        if alert.description:
            lines.append(f"- Detail: {alert.description}")
        raw = json.dumps(alert.source_ref, default=str, sort_keys=True)
        lines.append(f"- Raw source data: {raw}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _fire(rule, org, key_value, matching_alerts):
    """Create an incident and CorrelationFiring for a satisfied rule."""
    from incidents.models import Incident
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id
    from incidents.services.ioc_extraction import extract_and_save_iocs
    from correlations.models import CorrelationFiring
    from correlations.services.supersede import supersede_simpler_incidents

    title = f"{rule.name}: {key_value}"
    description = _compose_description(rule, key_value, matching_alerts)

    # Collect any simpler (non-correlation) incidents that currently own contributing alerts,
    # before relinking mutates alert.incident.
    prior_simpler = {
        a.incident
        for a in matching_alerts
        if a.incident_id is not None and a.incident.source_kind != Incident.SOURCE_CORRELATION
    }

    with transaction.atomic():
        ser = IncidentCreateSerializer(
            data={
                "title": title,
                "severity": rule.severity,
                "source_kind": "correlation",
                "description": description,
                "tlp": "amber",
                "pap": "amber",
            }
        )
        ser.is_valid(raise_exception=True)

        display_id = next_display_id()
        incident = ser.save(organization=org, display_id=display_id, created_by=None)

        record_event(
            incident,
            "incident_created",
            payload={"source": "correlation_rule", "rule_id": rule.id, "rule_name": rule.name},
        )

        for alert in matching_alerts:
            _link_alert_to_incident(alert, incident, rule)

        CorrelationFiring.objects.create(
            rule=rule,
            organization=org,
            entity_value=key_value,
            incident=incident,
        )

        if prior_simpler:
            supersede_simpler_incidents(incident, prior_simpler, rule)

        # Run IOC extraction over the now-populated description so the enrich +
        # triage pipeline (scheduled on commit by the Incident post_save signal)
        # has IOCs to enrich, matching the detection-suggestion path.
        extract_and_save_iocs(incident)

    return incident


def _evaluate_rule(rule, org, legs, key_value, alert):
    """Evaluate one rule for the given key value; fire or link-through as appropriate."""
    from correlations.models import CorrelationFiring

    # Dedup: if a live firing exists, link the alert to its incident and stop
    live_firing = (
        CorrelationFiring.objects
        .select_related("incident")
        .filter(rule=rule, organization=org, entity_value=key_value, incident__isnull=False)
        .exclude(incident__state=_CLOSED_STATE)
        .first()
    )

    if live_firing:
        if any(alert_matches_leg(alert, leg) for leg in legs):
            with transaction.atomic():
                _link_alert_to_incident(alert, live_firing.incident, rule)
        return

    # Check whether every leg is satisfied within the window
    window_start = timezone.now() - timedelta(minutes=rule.window_minutes)
    window_alerts = _get_window_alerts(org, rule.correlation_key, key_value, window_start)

    all_matching: set = set()
    for leg in legs:
        leg_hits = [a for a in window_alerts if alert_matches_leg(a, leg)]
        if len(leg_hits) < leg.count:
            return  # This leg is not satisfied — rule cannot fire
        all_matching.update(leg_hits)

    _fire(rule, org, key_value, all_matching)


def evaluate(alert):
    """Evaluate all applicable correlation rules against the alert."""
    from correlations.models import CorrelationRule, SystemRuleMute

    org = alert.organization

    muted_rule_ids = set(
        SystemRuleMute.objects.filter(organization=org).values_list("rule_id", flat=True)
    )

    rules = (
        CorrelationRule.objects.filter(enabled=True)
        .filter(models.Q(organization=None) | models.Q(organization=org))
        .prefetch_related("legs__conditions")
    )

    for rule in rules:
        if rule.organization_id is None and rule.id in muted_rule_ids:
            continue

        legs = list(rule.legs.all())
        if not legs:
            continue

        key_value = _correlation_key_value(alert, rule.correlation_key)
        if key_value is None:
            continue  # Alert lacks the required entity for this rule's correlation key

        try:
            _evaluate_rule(rule, org, legs, key_value, alert)
        except Exception:
            logger.exception(
                "evaluate: failed for rule %s alert %s", rule.id, alert.display_id
            )
