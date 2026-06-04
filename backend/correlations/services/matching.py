import json
from ipaddress import AddressValueError, ip_address, ip_network

from correlations.models import FIELD_KIND_ALERT, FIELD_KIND_ENTITY, FIELD_KIND_SOURCE_REF

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _field_values(alert, condition):
    """Return a list of values for the condition's field on the alert."""
    if condition.field_kind == FIELD_KIND_ALERT:
        v = getattr(alert, condition.field_name, None)
        return [v] if v is not None else []
    if condition.field_kind == FIELD_KIND_ENTITY:
        return list(
            alert.entities.filter(entity_type=condition.field_name).values_list("value", flat=True)
        )
    if condition.field_kind == FIELD_KIND_SOURCE_REF:
        v = (alert.source_ref or {}).get(condition.field_name)
        return [str(v)] if v is not None else []
    return []


def _matches(field_values, operator, cond_value):
    if not field_values:
        return False

    if operator == "equals":
        cv = cond_value.casefold()
        return any(str(v).casefold() == cv for v in field_values)

    if operator == "in":
        targets = {t.casefold() for t in json.loads(cond_value)}
        return any(str(v).casefold() in targets for v in field_values)

    if operator == "contains":
        cv = cond_value.casefold()
        return any(cv in str(v).casefold() for v in field_values)

    if operator == "gte":
        threshold = SEVERITY_ORDER.get(cond_value, -1)
        return any(SEVERITY_ORDER.get(str(v), -1) >= threshold for v in field_values)

    if operator == "lte":
        threshold = SEVERITY_ORDER.get(cond_value, -1)
        return any(SEVERITY_ORDER.get(str(v), -1) <= threshold for v in field_values)

    if operator == "cidr":
        try:
            network = ip_network(cond_value, strict=False)
        except ValueError:
            return False
        for v in field_values:
            try:
                if ip_address(str(v)) in network:
                    return True
            except (AddressValueError, ValueError):
                continue
        return False

    return False


def alert_matches_leg(alert, leg):
    """Return True if the alert satisfies every condition on the leg (AND semantics).

    Returns False when the leg has no conditions.
    """
    conditions = list(leg.conditions.all())
    if not conditions:
        return False
    return all(_matches(_field_values(alert, c), c.operator, c.value) for c in conditions)
