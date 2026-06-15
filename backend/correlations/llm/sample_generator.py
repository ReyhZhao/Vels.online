"""LLM-assisted Sample Document generator for Rule Tests (PRD #439 slice 5).

Drafts realistic should-fire (TP) / should-not-fire (TN) Sample Documents for a
Scheduled Search Rule, grounded in the live mapping and real sample docs (ADR-0007),
then sanitises them against the mapping. Never persists or runs anything — the author
reviews and saves the candidates.
"""
import logging

from correlations.llm.search_grounding import build_search_grounding

logger = logging.getLogger(__name__)

# Bound how many generated docs we keep, mirroring the test sample cap.
_MAX_GENERATED = 50


def _flatten(doc: dict, prefix: str = "") -> dict:
    """Flatten a nested doc to {dotted.path: value} for leaf paths."""
    flat = {}
    for key, value in doc.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _drop_unknown_paths(doc: dict, mapping: dict, prefix: str = "") -> tuple:
    """Recursively drop leaf paths absent from the mapping. Returns (clean_doc, dropped_paths).

    `@timestamp` is always kept (the window field). An empty mapping bypasses the check.
    """
    clean = {}
    dropped = []
    for key, value in doc.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            sub, sub_dropped = _drop_unknown_paths(value, mapping, path)
            dropped.extend(sub_dropped)
            if sub:
                clean[key] = sub
        else:
            if path == "@timestamp" or not mapping or path in mapping:
                clean[key] = value
            else:
                dropped.append(path)
    return clean, dropped


def sanitize_sample_docs(docs, mapping: dict) -> tuple:
    """Validate generated Sample Documents against the live mapping.

    Drops non-object docs, drops leaf fields absent from the mapping (with a warning),
    drops docs left without an @timestamp, and caps the count. Returns (clean_docs, warnings).
    Never persists or runs anything.
    """
    warnings = []
    clean_docs = []

    if not isinstance(docs, list):
        return [], ["Generator did not return a list of documents."]

    for i, doc in enumerate(docs[:_MAX_GENERATED]):
        if not isinstance(doc, dict):
            warnings.append(f"Document {i + 1}: not a JSON object; dropped.")
            continue
        clean, dropped = _drop_unknown_paths(doc, mapping)
        if dropped:
            warnings.append(
                f"Document {i + 1}: dropped field(s) absent from the index mapping: "
                f"{', '.join(sorted(dropped))}."
            )
        if "@timestamp" not in clean:
            warnings.append(f"Document {i + 1}: missing @timestamp; dropped.")
            continue
        clean_docs.append(clean)

    if len(docs) > _MAX_GENERATED:
        warnings.append(f"Generator returned {len(docs)} docs; kept the first {_MAX_GENERATED}.")

    return clean_docs, warnings


def _summarize_rule(rule) -> dict:
    return {
        "name": rule.name,
        "description": rule.description,
        "correlation_key": rule.correlation_key,
        "window_minutes": rule.window_minutes,
        "interval_minutes": rule.interval_minutes,
        "baseline_lookback_days": rule.baseline_lookback_days,
        "legs": [
            {
                "count": leg.count,
                "count_operator": leg.count_operator,
                "distinct_field": leg.distinct_field or None,
                "min_distinct": leg.min_distinct if leg.has_diversity else None,
                "novelty_field": leg.novelty_field or None,
                "conditions": [
                    {"field_name": c.field_name, "operator": c.operator, "value": c.value}
                    for c in leg.conditions.all()
                ],
            }
            for leg in rule.legs.prefetch_related("conditions")
        ],
    }


def build_sample_grounding(rule, scope=None, agent_ids=None) -> dict:
    """Grounding for sample generation: mapping + core/expanded fields + rule + real docs."""
    grounding = build_search_grounding(scope=scope, agent_ids=agent_ids)
    grounding["rule"] = _summarize_rule(rule)

    rule_ids = [
        c.value
        for leg in rule.legs.all()
        for c in leg.conditions.all()
        if c.field_name == "rule.id"
    ]
    try:
        from security.opensearch import OpenSearchClient, OpenSearchError
        try:
            grounding["sample_docs"] = OpenSearchClient().get_sample_docs(
                rule_ids=rule_ids or None, agent_ids=agent_ids, limit=5
            )
        except OpenSearchError:
            grounding["sample_docs"] = []
    except Exception:  # noqa: BLE001
        grounding["sample_docs"] = []

    return grounding


def generate_samples(rule, expect_fire: bool, scope=None, agent_ids=None) -> dict:
    """Generate + sanitise candidate Sample Documents. Returns {samples, warnings}.

    Raises DraftConfigError / DraftError from the provider layer; the caller maps these
    to HTTP responses. Never persists or runs anything.
    """
    from correlations.llm.factory import get_draft_provider

    grounding = build_sample_grounding(rule, scope=scope, agent_ids=agent_ids)
    provider = get_draft_provider()
    raw_samples = provider.generate_sample_docs(grounding, expect_fire)
    samples, warnings = sanitize_sample_docs(raw_samples, grounding.get("mapping", {}))
    return {"samples": samples, "warnings": warnings}
