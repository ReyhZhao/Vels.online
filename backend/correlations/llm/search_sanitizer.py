"""Mapping-aware sanitiser for LLM-drafted Scheduled Search Rules.

Unlike the correlation-rule sanitiser (which validates against a curated catalog),
this validates field_name + operator against the live index mapping per ADR-0007.
An empty mapping bypasses field validation (same behaviour as validate_search_field).
"""
from correlations.models import CORRELATION_KEY_CHOICES
from correlations.services.search_compiler import (
    _operators_for_type,
    validate_diversity_constraint,
)

_VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_VALID_CORR_KEYS = frozenset(k for k, _ in CORRELATION_KEY_CHOICES)


def sanitize_search_draft(draft: dict, mapping: dict) -> tuple:
    """Validate a search rule draft against the live field mapping.

    Strips invalid conditions/legs. Returns (sanitized_draft, warnings).
    Never persists or activates anything — caller is responsible for that.
    """
    warnings = []

    name = str(draft.get("name", "")).strip() or "Unnamed rule"
    description = str(draft.get("description", "")).strip()

    corr_key = draft.get("correlation_key", "none")
    if corr_key not in _VALID_CORR_KEYS:
        warnings.append(f"Unknown correlation key '{corr_key}'; defaulting to 'none'.")
        corr_key = "none"

    severity = draft.get("severity", "medium")
    if severity not in _VALID_SEVERITIES:
        warnings.append(f"Unknown severity '{severity}'; defaulting to 'medium'.")
        severity = "medium"

    def _coerce_int(val, default, minimum=1):
        try:
            return max(minimum, int(val))
        except (ValueError, TypeError):
            return default

    window = _coerce_int(draft.get("window_minutes"), 60)
    interval = _coerce_int(draft.get("interval_minutes"), 60, minimum=5)
    max_findings = _coerce_int(draft.get("max_findings_per_run"), 50)
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

            field_name = str(cond.get("field_name", "")).strip()
            operator = str(cond.get("operator", "")).strip()

            if not field_name:
                warnings.append(
                    f"Leg {leg_i + 1} condition {cond_i + 1}: missing field_name; condition removed."
                )
                continue

            # Validate against live mapping when available.
            if mapping:
                if field_name not in mapping:
                    warnings.append(
                        f"Leg {leg_i + 1} condition {cond_i + 1}: "
                        f"'{field_name}' not found in index mapping; condition removed."
                    )
                    continue

                valid_ops = set(_operators_for_type(mapping[field_name]))
                if operator not in valid_ops:
                    warnings.append(
                        f"Leg {leg_i + 1} condition {cond_i + 1}: "
                        f"operator '{operator}' not valid for '{field_name}' "
                        f"(type: {mapping[field_name]}); condition removed."
                    )
                    continue

            sanitized_conditions.append({
                "field_name": field_name,
                "operator": operator,
                "value": str(cond.get("value", "")),
            })

        count = _coerce_int(leg.get("count"), 1)

        sanitized_leg = {
            "count": count,
            "display_order": leg_i,
            "conditions": sanitized_conditions,
        }

        # Diversity Constraint (ADR-0009): preserve when valid, else strip with an
        # unmistakable warning (the constraint is load-bearing — a silent strip would
        # leave a draft that looks fine but no longer checks distinct values).
        distinct_field = str(leg.get("distinct_field", "")).strip()
        if distinct_field:
            raw_min = leg.get("min_distinct", 2)
            ok, reason = validate_diversity_constraint(distinct_field, raw_min, corr_key, mapping)
            if ok:
                sanitized_leg["distinct_field"] = distinct_field
                sanitized_leg["min_distinct"] = max(2, int(raw_min))
            else:
                warnings.append(
                    f"⚠ Leg {leg_i + 1}: diversity constraint on '{distinct_field}' was REMOVED — "
                    f"this rule no longer checks for distinct values. {reason} "
                    f"Re-add the diversity constraint in the builder before saving."
                )

        sanitized_legs.append(sanitized_leg)

    return {
        "name": name,
        "description": description,
        "correlation_key": corr_key,
        "severity": severity,
        "window_minutes": window,
        "interval_minutes": interval,
        "max_findings_per_run": max_findings,
        "enabled": enabled,
        "legs": sanitized_legs,
    }, warnings
