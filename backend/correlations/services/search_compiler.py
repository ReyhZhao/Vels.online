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


def compile_query(
    conditions,
    agent_ids,
    window_start,
    window_end,
    max_size: int,
    key_field: str | None = None,
    key_value: str | None = None,
    field_mapping: dict | None = None,
) -> dict:
    """Build an OpenSearch search body scoped to agent_ids and bounded to [window_start, window_end].

    If key_field and key_value are supplied an additional term filter is added so results are
    restricted to documents matching that specific correlation key value.
    field_mapping is forwarded to _condition_to_clause for type-aware DSL generation.
    """
    filters = [
        {"terms": {"agent.id": [str(a) for a in agent_ids]}},
        {
            "range": {
                "@timestamp": {
                    "gte": window_start.isoformat(),
                    "lte": window_end.isoformat(),
                }
            }
        },
    ]

    if key_field and key_value is not None:
        filters.append({"term": {key_field: key_value}})

    for condition in conditions:
        clause = _condition_to_clause(condition, field_mapping)
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
) -> dict:
    """Build an OpenSearch body that returns a terms aggregation on key_field with no hits.

    Used by the multi-leg evaluator to count matches per key before fetching documents.
    field_mapping is forwarded to _condition_to_clause for type-aware DSL generation.
    """
    base = compile_query(
        conditions, agent_ids, window_start, window_end, max_size=0, field_mapping=field_mapping
    )
    base["aggregations"] = {
        "key_agg": {
            "terms": {
                "field": key_field,
                "size": max_buckets,
            }
        }
    }
    return base
