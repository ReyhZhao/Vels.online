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
    FIELD_KIND_ALERT: sorted(ALERT_FIELD_CATALOG),
    FIELD_KIND_ENTITY: sorted(ENTITY_CATALOG),
    FIELD_KIND_SOURCE_REF: sorted(SOURCE_REF_CATALOG),
}

_ALLOWED_OPERATORS = {
    FIELD_KIND_ALERT: sorted({"equals", "in", "contains", "gte", "lte"}),
    FIELD_KIND_ENTITY: sorted({"equals", "in", "contains", "cidr"}),
    FIELD_KIND_SOURCE_REF: sorted({"equals", "in", "contains"}),
}


def build_grounding(scope=None) -> dict:
    """Return vocabulary-only grounding for the default scope (v1: no alert sampling)."""
    return {
        "field_catalog": _FIELD_CATALOG,
        "allowed_operators": _ALLOWED_OPERATORS,
        "severities": ["critical", "high", "medium", "low", "info"],
        "correlation_keys": [k for k, _ in CORRELATION_KEY_CHOICES],
    }
