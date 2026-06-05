from correlations.models import (
    ALERT_FIELD_CATALOG,
    CORRELATION_KEY_CHOICES,
    ENTITY_CATALOG,
    FIELD_KIND_ALERT,
    FIELD_KIND_ENTITY,
    FIELD_KIND_SOURCE_REF,
    SOURCE_REF_CATALOG,
)

_FIELD_CATALOG = {
    FIELD_KIND_ALERT: frozenset(ALERT_FIELD_CATALOG),
    FIELD_KIND_ENTITY: frozenset(ENTITY_CATALOG),
    FIELD_KIND_SOURCE_REF: frozenset(SOURCE_REF_CATALOG),
}

_ALLOWED_OPERATORS = {
    FIELD_KIND_ALERT: frozenset({"equals", "in", "contains", "gte", "lte"}),
    FIELD_KIND_ENTITY: frozenset({"equals", "in", "contains", "cidr"}),
    FIELD_KIND_SOURCE_REF: frozenset({"equals", "in", "contains"}),
}

_VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_VALID_CORR_KEYS = frozenset(k for k, _ in CORRELATION_KEY_CHOICES)


def sanitize_draft(draft: dict) -> tuple:
    """
    Validate draft against field catalog + operator rules.
    Strips invalid conditions/legs and returns (sanitized_draft, warnings).
    The returned draft is guaranteed to pass the save serializer's constraints.
    """
    warnings = []

    name = str(draft.get("name", "")).strip() or "Unnamed rule"
    description = str(draft.get("description", "")).strip()

    corr_key = draft.get("correlation_key", "none")
    if corr_key not in _VALID_CORR_KEYS:
        warnings.append(f"Unknown correlation key '{corr_key}'; defaulting to 'none'.")
        corr_key = "none"

    try:
        window = max(1, int(draft.get("window_minutes", 60)))
    except (ValueError, TypeError):
        window = 60

    severity = draft.get("severity", "medium")
    if severity not in _VALID_SEVERITIES:
        warnings.append(f"Unknown severity '{severity}'; defaulting to 'medium'.")
        severity = "medium"

    enabled = bool(draft.get("enabled", True))

    sanitized_legs = []
    for leg_i, leg in enumerate(draft.get("legs", [])):
        if not isinstance(leg, dict):
            warnings.append(f"Leg {leg_i + 1}: invalid structure; leg removed.")
            continue

        sanitized_conditions = []
        for cond_i, cond in enumerate(leg.get("conditions", [])):
            if not isinstance(cond, dict):
                warnings.append(
                    f"Leg {leg_i + 1} condition {cond_i + 1}: invalid structure; condition removed."
                )
                continue

            field_kind = cond.get("field_kind", "")
            field_name = cond.get("field_name", "")
            operator = cond.get("operator", "")

            catalog = _FIELD_CATALOG.get(field_kind)
            if catalog is None:
                warnings.append(
                    f"Leg {leg_i + 1} condition {cond_i + 1}: "
                    f"unknown field kind '{field_kind}'; condition removed."
                )
                continue

            if field_name not in catalog:
                warnings.append(
                    f"Leg {leg_i + 1} condition {cond_i + 1}: "
                    f"unknown field '{field_name}' for kind '{field_kind}'; condition removed."
                )
                continue

            allowed_ops = _ALLOWED_OPERATORS.get(field_kind, frozenset())
            if operator not in allowed_ops:
                warnings.append(
                    f"Leg {leg_i + 1} condition {cond_i + 1}: "
                    f"operator '{operator}' not allowed for field kind '{field_kind}'; condition removed."
                )
                continue

            sanitized_conditions.append({
                "field_kind": field_kind,
                "field_name": field_name,
                "operator": operator,
                "value": str(cond.get("value", "")),
            })

        try:
            count = max(1, int(leg.get("count", 1)))
        except (ValueError, TypeError):
            count = 1

        sanitized_legs.append({
            "count": count,
            "display_order": leg_i,
            "conditions": sanitized_conditions,
        })

    return {
        "name": name,
        "description": description,
        "correlation_key": corr_key,
        "window_minutes": window,
        "severity": severity,
        "enabled": enabled,
        "legs": sanitized_legs,
    }, warnings
