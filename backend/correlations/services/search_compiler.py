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


def _condition_to_clause(condition) -> dict | None:
    field = condition.field_name
    op = condition.operator
    value = condition.value

    if op == SEARCH_OPERATOR_EQUALS:
        return {"term": {field: value}}
    if op == SEARCH_OPERATOR_CONTAINS:
        return {"match": {field: value}}
    if op == SEARCH_OPERATOR_GTE:
        return {"range": {field: {"gte": value}}}
    if op == SEARCH_OPERATOR_LTE:
        return {"range": {field: {"lte": value}}}
    if op == SEARCH_OPERATOR_CIDR:
        # OpenSearch ip-type fields accept CIDR in term queries
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
) -> dict:
    """Build an OpenSearch search body scoped to agent_ids and bounded to [window_start, window_end].

    If key_field and key_value are supplied an additional term filter is added so results are
    restricted to documents matching that specific correlation key value.
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
        clause = _condition_to_clause(condition)
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
) -> dict:
    """Build an OpenSearch body that returns a terms aggregation on key_field with no hits.

    Used by the multi-leg evaluator to count matches per key before fetching documents.
    """
    base = compile_query(conditions, agent_ids, window_start, window_end, max_size=0)
    base["aggregations"] = {
        "key_agg": {
            "terms": {
                "field": key_field,
                "size": max_buckets,
            }
        }
    }
    return base
