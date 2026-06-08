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
_VALID_TIME_WINDOW_MODES = frozenset({"inside", "outside"})


def _sanitize_time_window(draft: dict, warnings: list) -> dict:
    """Validate the optional time-of-day window (#440) on an LLM draft.

    Returns the window fields the drawer/serializer expect. A window is only kept when
    start, end, and a non-empty valid day set are all present; otherwise it is cleared
    (no constraint). Invalid pieces are dropped with a warning rather than raising.
    """
    cleared = {
        "time_window_start": None,
        "time_window_end": None,
        "time_window_days": [],
        "time_window_mode": "inside",
    }

    def _parse_time(val):
        """Accept 'HH:MM' or 'HH:MM:SS'; return normalised 'HH:MM:SS' or None."""
        if not val:
            return None
        parts = str(val).strip().split(":")
        if len(parts) < 2:
            return None
        try:
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, TypeError):
            return None
        if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
            return None
        return f"{h:02d}:{m:02d}:{s:02d}"

    start = _parse_time(draft.get("time_window_start"))
    end = _parse_time(draft.get("time_window_end"))

    raw_days = draft.get("time_window_days") or []
    days = []
    if isinstance(raw_days, (list, tuple)):
        for d in raw_days:
            try:
                di = int(d)
            except (ValueError, TypeError):
                continue
            if 1 <= di <= 7 and di not in days:
                days.append(di)
    days.sort()

    mode = draft.get("time_window_mode", "inside")
    if mode not in _VALID_TIME_WINDOW_MODES:
        mode = "inside"

    # Anything set at all signals the LLM intended a window — validate as a group.
    any_set = bool(draft.get("time_window_start") or draft.get("time_window_end") or raw_days)
    if not any_set:
        return cleared

    if not (start and end):
        warnings.append("Time-of-day window dropped: both a start and end time are required.")
        return cleared
    if start == end:
        warnings.append("Time-of-day window dropped: start and end times must differ.")
        return cleared
    if not days:
        warnings.append("Time-of-day window dropped: at least one day of week is required.")
        return cleared

    return {
        "time_window_start": start,
        "time_window_end": end,
        "time_window_days": days,
        "time_window_mode": mode,
    }


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

    time_window = _sanitize_time_window(draft, warnings)

    return {
        "name": name,
        "description": description,
        "correlation_key": corr_key,
        "severity": severity,
        "window_minutes": window,
        "interval_minutes": interval,
        "max_findings_per_run": max_findings,
        "enabled": enabled,
        **time_window,
        "legs": sanitized_legs,
    }, warnings
