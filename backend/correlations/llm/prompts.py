"""System prompt for the Correlation Rule author assistant.

The prompt template and the grounding-to-prompt builder live here so the wording
can be tuned without touching provider code. Both the Gemini and Ollama draft
providers use ``_build_system_prompt``. (Search-rule prompts live in
``search_prompt.py``.)
"""
import json

_SYSTEM_PROMPT_TEMPLATE = """\
You are a security rule-author assistant. Given a natural-language description of a detection \
scenario, draft a Correlation Rule for a SIEM platform.

Return a JSON object with exactly these fields:
  draft_rule      (object, required) — the drafted Correlation Rule (schema below)
  assistant_reply (string, required) — 1-3 sentence plain-language explanation of what the rule \
detects and why you chose these parameters

draft_rule schema:
{{
  "name": "string (required) — short descriptive rule name",
  "description": "string — what the rule detects",
  "correlation_key": "string — one of: {corr_keys}",
  "window_minutes": integer (min 1),
  "severity": "string — one of: {severities}",
  "enabled": true,
  "legs": [
    {{
      "count": integer (min 1) — minimum matching alerts required,
      "display_order": integer — 0-indexed position,
      "conditions": [
        {{
          "field_kind": "one of: alert_field, entity, source_ref",
          "field_name": "valid field name for the field_kind (see vocabulary)",
          "operator": "valid operator for the field_kind (see vocabulary)",
          "value": "string"
        }}
      ]
    }}
  ]
}}

Vocabulary (only use these exact values):
{vocabulary}

Alert corpus (real data from this scope — prefer these values when proposing conditions):
{corpus}

Rules:
- Only use field names and operators listed in the vocabulary above
- Prefer condition values that appear in the alert corpus above (e.g. real source_kinds, rule_ids, \
titles, entity values) rather than invented examples
- A rule must have at least one leg with at least one condition
- If a current draft is provided, update it based on the latest instruction
- Return only valid JSON. No markdown, no code fences, no explanation outside the JSON.
"""


def _build_system_prompt(grounding: dict) -> str:
    vocab_parts = []
    field_catalog = grounding.get("field_catalog", {})
    allowed_ops = grounding.get("allowed_operators", {})
    for kind, fields in field_catalog.items():
        ops = allowed_ops.get(kind, [])
        vocab_parts.append(f"  {kind}: fields={fields}, operators={ops}")

    corpus_parts = []

    source_kinds = grounding.get("source_kinds", {})
    if source_kinds:
        corpus_parts.append(f"  source_kinds present: {source_kinds}")

    sev_dist = grounding.get("severity_distribution", {})
    if sev_dist:
        corpus_parts.append(f"  severity distribution: {sev_dist}")

    entity_types = grounding.get("entity_types", [])
    if entity_types:
        corpus_parts.append(f"  entity types populated: {entity_types}")

    sr_keys = grounding.get("source_ref_keys", [])
    if sr_keys:
        corpus_parts.append(f"  source_ref keys present: {sr_keys}")

    top_values = grounding.get("top_values", {})
    if top_values.get("alert_field"):
        corpus_parts.append(f"  top alert field values: {top_values['alert_field']}")
    if top_values.get("entity"):
        corpus_parts.append(f"  top entity values: {top_values['entity']}")
    if top_values.get("source_ref"):
        corpus_parts.append(f"  top source_ref values: {top_values['source_ref']}")

    sample_alerts = grounding.get("sample_alerts", [])
    if sample_alerts:
        corpus_parts.append(f"  sample alerts (most recent first):\n{json.dumps(sample_alerts, indent=2)}")

    corpus_section = "\n".join(corpus_parts) if corpus_parts else "  (no alert data in scope)"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        corr_keys=", ".join(grounding.get("correlation_keys", [])),
        severities=", ".join(grounding.get("severities", [])),
        vocabulary="\n".join(vocab_parts),
        corpus=corpus_section,
    )
