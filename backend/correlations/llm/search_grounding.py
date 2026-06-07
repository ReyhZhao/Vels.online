"""Grounding builder for the Scheduled Search Rule author assistant (ADR-0007).

Two-stage grounding aligned with two-pass drafting:
- Stage 1 (pass 1): rule_catalog + mapping overview → LLM selects relevant rule.ids
- Stage 2 (pass 2): expand_rule_fields() adds populated fields + top values for selected ids
"""
from django.conf import settings

from security.models import Organization

_WINDOW_DAYS = 7
_TOP_VALUES_CAP = 15
_MAX_CATALOG_RULES = 200  # cap for prompt safety

# Curated core fields — always present in grounding regardless of expansion.
_SEARCH_CORE_FIELDS = [
    {"value": "rule.id",           "type": "keyword"},
    {"value": "rule.level",        "type": "long"},
    {"value": "rule.description",  "type": "text"},
    {"value": "rule.groups",       "type": "keyword"},
    {"value": "agent.name",        "type": "keyword"},
    {"value": "agent.id",          "type": "keyword"},
    {"value": "data.srcip",        "type": "ip"},
    {"value": "data.dstip",        "type": "ip"},
    {"value": "data.dstuser",      "type": "keyword"},
    {"value": "data.audit.comm",   "type": "keyword"},
    {"value": "data.sha256",       "type": "keyword"},
]


def _bounds():
    return (
        int(getattr(settings, "SEARCH_GROUNDING_WINDOW_DAYS", _WINDOW_DAYS)),
        int(getattr(settings, "GROUNDING_VALUE_CAP", _TOP_VALUES_CAP)),
    )


def _org_for_scope(scope):
    try:
        return Organization.objects.get(slug=scope)
    except Organization.DoesNotExist:
        return None


def build_search_grounding(scope=None, agent_ids=None) -> dict:
    """Build the base grounding payload for the search rule drafter.

    Contains rule_catalog, mapping, core_fields, severities, correlation_keys.
    expanded_fields starts empty and is filled in by expand_rule_fields() after pass 1.
    """
    from security.opensearch import OpenSearchClient, OpenSearchError

    window_days, _ = _bounds()

    client = OpenSearchClient()

    mapping: dict = {}
    try:
        mapping = client.get_field_mapping()
    except OpenSearchError:
        pass

    rule_catalog: dict = {}
    try:
        rule_catalog = client.get_rule_catalog(agent_ids=agent_ids, window_days=window_days)
    except OpenSearchError:
        pass

    if len(rule_catalog) > _MAX_CATALOG_RULES:
        top = sorted(rule_catalog.items(), key=lambda x: x[1]["seen_count"], reverse=True)
        rule_catalog = dict(top[:_MAX_CATALOG_RULES])

    return {
        "rule_catalog": rule_catalog,
        "mapping": mapping,
        "core_fields": _SEARCH_CORE_FIELDS,
        "severities": ["critical", "high", "medium", "low", "info"],
        "correlation_keys": [
            {"value": "none",             "wazuh_field": None,             "label": "None (org-wide)"},
            {"value": "host.name",        "wazuh_field": "agent.name",     "label": "Host"},
            {"value": "source.ip",        "wazuh_field": "data.srcip",     "label": "Source IP"},
            {"value": "user.name",        "wazuh_field": "data.dstuser",   "label": "Username"},
            {"value": "file.hash.sha256", "wazuh_field": "data.sha256",    "label": "File Hash"},
            {"value": "process.name",     "wazuh_field": "data.audit.comm","label": "Process"},
        ],
        "expanded_fields": {},
    }


def expand_rule_fields(rule_ids: list, agent_ids=None, mapping: dict = None) -> dict:
    """Lazily fetch populated fields + top values for the given rule.ids.

    Returns {field_path: {type, top_values, operators}} scoped to those rules.
    Called between pass 1 (rule selection) and pass 2 (drafting).
    """
    from security.opensearch import OpenSearchClient, OpenSearchError

    if not rule_ids:
        return {}

    mapping = mapping or {}
    client = OpenSearchClient()

    _, value_cap = _bounds()
    window_days, _ = _bounds()

    try:
        return client.get_fields_for_rules(
            rule_ids=rule_ids,
            agent_ids=agent_ids,
            window_days=window_days,
            mapping=mapping,
            top_values_cap=value_cap,
        )
    except OpenSearchError:
        return {}
