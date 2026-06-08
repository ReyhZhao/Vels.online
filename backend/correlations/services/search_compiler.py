"""OpenSearch DSL compiler for SearchLegCondition instances."""
import logging

from correlations.models import (
    SEARCH_OPERATOR_CIDR,
    SEARCH_OPERATOR_CONTAINS,
    SEARCH_OPERATOR_EQUALS,
    SEARCH_OPERATOR_GTE,
    SEARCH_OPERATOR_LTE,
)

logger = logging.getLogger(__name__)

_ALERTS_INDEX = "wazuh-alerts-4.x-*"

# Canonical correlation-key value → Wazuh document field used for aggregation.
CORRELATION_KEY_TO_WAZUH_FIELD = {
    "host.name": "agent.name",
    "source.ip": "data.srcip",
    "user.name": "data.dstuser",
    "file.hash.sha256": "data.sha256",
    "process.name": "data.audit.comm",
}

_DEFAULT_AGG_MAX_BUCKETS = 500

# Size cap for the Diversity Constraint distinct-value sub-aggregation (ADR-0009).
# Bounds the cost of a `terms` sub-agg when distinct_field is high-cardinality.
_DISTINCT_SUBAGG_SIZE = 50

# Field types that are not aggregatable (cannot be used as correlation key).
_TEXT_TYPES = frozenset({"text", "match_only_text"})

_NUMERIC_TYPES = frozenset({
    "long", "integer", "short", "byte",
    "double", "float", "half_float", "scaled_float", "unsigned_long",
})

_DATE_TYPES = frozenset({"date", "date_nanos"})
_IP_TYPES = frozenset({"ip"})


def _operators_for_type(field_type: str) -> list:
    """Return the list of valid search operators for a given field type."""
    if field_type in _NUMERIC_TYPES or field_type in _DATE_TYPES:
        return [SEARCH_OPERATOR_EQUALS, SEARCH_OPERATOR_GTE, SEARCH_OPERATOR_LTE]
    if field_type in _IP_TYPES:
        return [SEARCH_OPERATOR_EQUALS, SEARCH_OPERATOR_CIDR]
    # keyword, text, boolean, and unknown types
    return [SEARCH_OPERATOR_EQUALS, SEARCH_OPERATOR_CONTAINS]


def validate_search_field(field: str, operator: str, mapping: dict) -> tuple[bool, str]:
    """Return (True, "") if field+operator is valid against mapping, else (False, reason).

    A field absent from the mapping is always invalid. The caller is responsible for
    supplying a non-empty mapping; an empty mapping bypasses validation.
    """
    if not mapping:
        return True, ""

    if field not in mapping:
        return False, f"'{field}' does not exist in the index mapping."

    field_type = mapping[field]
    valid_ops = set(_operators_for_type(field_type))
    if operator not in valid_ops:
        return False, (
            f"Operator '{operator}' is not valid for field '{field}' (type: {field_type}). "
            f"Valid operators: {sorted(valid_ops)}."
        )

    return True, ""


def is_aggregatable_field(field: str, mapping: dict) -> bool:
    """Return False if the field type is non-aggregatable (text); True otherwise."""
    return mapping.get(field, "keyword") not in _TEXT_TYPES


def _agg_target(field: str, mapping: dict | None) -> str:
    """Resolve the aggregatable form of a field: text → its .keyword subfield."""
    if mapping and mapping.get(field) in _TEXT_TYPES:
        return f"{field}.keyword"
    return field


def validate_diversity_constraint(
    distinct_field: str, min_distinct, correlation_key: str, mapping: dict
) -> tuple[bool, str]:
    """Validate a leg's Diversity Constraint (ADR-0009).

    Returns (True, "") when there is no constraint (empty distinct_field) or it is valid;
    otherwise (False, reason). The four invariants:
      1. requires a non-'none' correlation key to group by,
      2. min_distinct must be >= 2 (a floor of 1 is satisfied by every non-empty bucket),
      3. distinct_field must be aggregatable (text resolved via .keyword) and present,
      4. distinct_field must not resolve to the same Wazuh field as the correlation key.
    An empty mapping bypasses the existence/type checks (consistent with validate_search_field).
    """
    from correlations.models import CORRELATION_KEY_NONE

    if not distinct_field:
        return True, ""

    if correlation_key == CORRELATION_KEY_NONE:
        return False, (
            "A diversity constraint requires a correlation key to group by "
            "(correlation_key cannot be 'none')."
        )

    try:
        md = int(min_distinct)
    except (TypeError, ValueError):
        md = 0
    if md < 2:
        return False, (
            "min_distinct must be at least 2 for a diversity constraint "
            "(a threshold of 1 is satisfied by any single value)."
        )

    base = distinct_field[: -len(".keyword")] if distinct_field.endswith(".keyword") else distinct_field
    key_field = CORRELATION_KEY_TO_WAZUH_FIELD.get(correlation_key)
    if key_field and base == key_field:
        return False, (
            f"distinct_field '{distinct_field}' must differ from the correlation key field "
            f"'{key_field}' — a key cannot diversify on itself (the rule could never fire)."
        )

    if mapping:
        if distinct_field not in mapping and base not in mapping:
            return False, f"distinct_field '{distinct_field}' does not exist in the index mapping."
        if not is_aggregatable_field(base, mapping):
            return False, (
                f"distinct_field '{distinct_field}' is a non-aggregatable text field "
                f"and cannot be used for a diversity constraint."
            )

    return True, ""


def _condition_to_clause(condition, field_mapping: dict | None = None) -> dict | None:
    """Convert a SearchLegCondition to an OpenSearch filter clause.

    field_mapping, if provided, is used to select the correct DSL form:
      - text + equals  → term on {field}.keyword
      - ip + cidr      → term (OpenSearch evaluates CIDR on ip fields)
      - numeric/date   → range for gte/lte
    """
    field = condition.field_name
    op = condition.operator
    value = condition.value
    field_type = (field_mapping or {}).get(field, "keyword")

    if op == SEARCH_OPERATOR_EQUALS:
        target = f"{field}.keyword" if field_type in _TEXT_TYPES else field
        return {"term": {target: value}}
    if op == SEARCH_OPERATOR_CONTAINS:
        return {"match": {field: value}}
    if op == SEARCH_OPERATOR_GTE:
        return {"range": {field: {"gte": value}}}
    if op == SEARCH_OPERATOR_LTE:
        return {"range": {field: {"lte": value}}}
    if op == SEARCH_OPERATOR_CIDR:
        return {"term": {field: value}}

    logger.warning("search_compiler: unknown operator %r — skipping condition", op)
    return None


def build_time_of_day_filter(rule, tz_name: str | None) -> dict | None:
    """Build an OpenSearch script filter for a rule's time-of-day window (#440).

    Returns a painless `script` filter clause that keeps only documents whose
    `@timestamp`, converted to *tz_name* (the owning org's timezone), falls inside
    (or outside, per `time_window_mode`) the [start, end) window on the selected ISO
    weekdays (1=Mon … 7=Sun). Windows that cross midnight (start > end) are supported.
    Returns None when the rule has no active window (behaviour unchanged).
    """
    if not getattr(rule, "has_time_window", False):
        return None

    start = rule.time_window_start
    end = rule.time_window_end
    days = [int(d) for d in (rule.time_window_days or [])]
    mode = getattr(rule, "time_window_mode", None) or "inside"
    inside = mode != "outside"

    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute

    source = (
        "ZonedDateTime z = doc['@timestamp'].value.withZoneSameInstant(ZoneId.of(params.tz)); "
        "int dow = z.getDayOfWeek().getValue(); "
        "int m = z.getHour() * 60 + z.getMinute(); "
        "boolean day = params.days.contains(dow); "
        "boolean win; "
        "if (params.start <= params.end) { win = day && m >= params.start && m < params.end; } "
        "else { win = day && (m >= params.start || m < params.end); } "
        "return params.inside ? win : !win;"
    )
    return {
        "script": {
            "script": {
                "lang": "painless",
                "source": source,
                "params": {
                    "tz": tz_name or "UTC",
                    "days": days,
                    "start": start_min,
                    "end": end_min,
                    "inside": inside,
                },
            }
        }
    }


def compile_query(
    conditions,
    agent_ids,
    window_start,
    window_end,
    max_size: int,
    key_field: str | None = None,
    key_value: str | None = None,
    field_mapping: dict | None = None,
    extra_filters: list | None = None,
) -> dict:
    """Build an OpenSearch search body bounded to [window_start, window_end].

    agent_ids: when a non-empty list, restricts results to those agents; when None,
    no agent filter is applied (agentless/infrastructure mode).
    If key_field and key_value are supplied an additional term filter is added so results are
    restricted to documents matching that specific correlation key value.
    field_mapping is forwarded to _condition_to_clause for type-aware DSL generation.
    extra_filters: additional bool-filter clauses appended verbatim (e.g. the time-of-day
    window filter, #440), so leg counts/diversity are evaluated over the filtered set.
    """
    filters = []
    if agent_ids is not None:
        filters.append({"terms": {"agent.id": [str(a) for a in agent_ids]}})
    filters.append({
        "range": {
            "@timestamp": {
                "gte": window_start.isoformat(),
                "lte": window_end.isoformat(),
            }
        }
    })

    if key_field and key_value is not None:
        filters.append({"term": {key_field: key_value}})

    for condition in conditions:
        clause = _condition_to_clause(condition, field_mapping)
        if clause is not None:
            filters.append(clause)

    if extra_filters:
        for clause in extra_filters:
            if clause is not None:
                filters.append(clause)

    return {
        "query": {"bool": {"filter": filters}},
        "size": max_size,
        "_source": True,
    }


def compile_agg_query(
    conditions,
    agent_ids,
    window_start,
    window_end,
    key_field: str,
    max_buckets: int = _DEFAULT_AGG_MAX_BUCKETS,
    field_mapping: dict | None = None,
    distinct_field: str | None = None,
    distinct_size: int = _DISTINCT_SUBAGG_SIZE,
    extra_filters: list | None = None,
) -> dict:
    """Build an OpenSearch body that returns a terms aggregation on key_field with no hits.

    Used by the multi-leg evaluator to count matches per key before fetching documents.
    field_mapping is forwarded to _condition_to_clause for type-aware DSL generation.

    When distinct_field is supplied (Diversity Constraint, ADR-0009), a size-capped `terms`
    sub-aggregation is nested under key_agg so each key bucket carries the distinct values
    (and per-value doc_count) of distinct_field. The sub-agg target is resolved to its
    .keyword subfield for text-typed fields.
    """
    base = compile_query(
        conditions, agent_ids, window_start, window_end, max_size=0,
        field_mapping=field_mapping, extra_filters=extra_filters,
    )
    key_agg: dict = {
        "terms": {
            "field": key_field,
            "size": max_buckets,
        }
    }
    if distinct_field:
        key_agg["aggregations"] = {
            "distinct_agg": {
                "terms": {
                    "field": _agg_target(distinct_field, field_mapping),
                    "size": distinct_size,
                }
            }
        }
    base["aggregations"] = {"key_agg": key_agg}
    return base
