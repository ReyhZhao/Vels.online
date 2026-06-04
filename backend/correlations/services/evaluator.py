import logging

from django.db import models, transaction

from correlations.services.matching import alert_matches_leg

logger = logging.getLogger(__name__)


def _correlation_key_value(alert, correlation_key):
    """Return the correlation key value for the alert, or 'none' for key='none'."""
    if correlation_key == "none":
        return "none"
    entity = alert.entities.filter(entity_type=correlation_key).first()
    return entity.value if entity else "unknown"


def _fire_single_leg(rule, alert, org, key_value):
    """Create an incident and firing record for a matching single-leg rule."""
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id
    from correlations.models import CorrelationFiring

    title = f"{rule.name}: {key_value}"

    with transaction.atomic():
        ser = IncidentCreateSerializer(
            data={
                "title": title,
                "severity": rule.severity,
                "source_kind": "correlation",
                "description": "",
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

        alert.state = "imported"
        alert.incident = incident
        alert.save(update_fields=["state", "incident", "updated_at"])

        record_event(
            incident,
            "alert_linked",
            payload={"alert_display_id": alert.display_id, "source": "correlation_rule", "rule_name": rule.name},
        )

        CorrelationFiring.objects.create(
            rule=rule,
            organization=org,
            entity_value=key_value,
            incident=incident,
        )

    return incident


def evaluate(alert):
    """Evaluate all applicable correlation rules against the alert.

    For this slice only single-leg rules are supported; they fire immediately
    without any windowing.  The synchronous fast-path (route_alert) is untouched.
    """
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
        if len(legs) != 1:
            continue

        leg = legs[0]
        if not alert_matches_leg(alert, leg):
            continue

        key_value = _correlation_key_value(alert, rule.correlation_key)

        try:
            _fire_single_leg(rule, alert, org, key_value)
        except Exception:
            logger.exception(
                "evaluate: failed to fire rule %s for alert %s", rule.id, alert.display_id
            )
