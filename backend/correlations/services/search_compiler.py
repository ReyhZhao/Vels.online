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


def compile_query(conditions, agent_ids, window_start, window_end, max_size: int) -> dict:
    """Build an OpenSearch search body scoped to agent_ids and bounded to [window_start, window_end]."""
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

    for condition in conditions:
        clause = _condition_to_clause(condition)
        if clause is not None:
            filters.append(clause)

    return {
        "query": {"bool": {"filter": filters}},
        "size": max_size,
        "_source": True,
    }
