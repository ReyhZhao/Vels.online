"""System-prompt builders for the two-pass Scheduled Search Rule drafter."""
import json

_RULE_SELECTION_TEMPLATE = """\
You are a security analyst assistant. Given the user's threat description, identify which \
Wazuh rule.ids from the catalog below are most relevant to what they want to detect.

Return a JSON object with exactly these fields:
  selected_rule_ids (array of strings) — up to 20 most relevant rule.id values from the catalog
  selection_reasoning (string) — 1-2 sentence explanation of why these rules are relevant

Wazuh rule catalog ({count} rules seen in the past {window_days} days):
{catalog_text}

Rules:
- Only select rule.id values that appear in the catalog above
- Return at most 20 rule.ids
- If the user's description is broad, prefer commonly-seen rules (high seen_count)
- Return only valid JSON. No markdown, no code fences, no explanation outside the JSON.
"""

_SEARCH_DRAFT_TEMPLATE = """\
You are a security rule-author assistant. Given a natural-language description, \
draft a Scheduled Search Rule that periodically queries raw Wazuh alert events in OpenSearch.

Return a JSON object with exactly these fields:
  draft_rule      (object, required) — the drafted Scheduled Search Rule (schema below)
  assistant_reply (string, required) — 1-3 sentence plain-language explanation

draft_rule schema:
{{
  "name": "string (required) — short descriptive rule name",
  "description": "string — what the rule detects",
  "correlation_key": "string — one of: {corr_keys}",
  "window_minutes": integer (min 1) — lookback window for each run,
  "interval_minutes": integer (min 5) — how often the rule runs,
  "max_findings_per_run": integer (min 1, default 50),
  "severity": "string — one of: {severities}",
  "enabled": true,
  "legs": [
    {{
      "count": integer (min 1) — minimum matching docs required in this leg,
      "display_order": integer — 0-indexed position,
      "distinct_field": "string (optional) — Diversity Constraint: an aggregatable Wazuh field. The leg fires only when its matches span at least min_distinct DISTINCT values of this field for the same correlation key. Leave empty for no constraint.",
      "min_distinct": integer (min 2, default 2) — required when distinct_field is set,
      "conditions": [
        {{
          "field_name": "Wazuh document field path (e.g. rule.id, agent.name, data.srcip)",
          "operator": "one of: equals, contains, gte, lte, cidr",
          "value": "string"
        }}
      ]
    }}
  ]
}}

Operator rules by field type:
  keyword / boolean / unknown : equals, contains
  numeric (long, integer, etc.) / date : equals, gte, lte
  ip : equals, cidr

Correlation key → Wazuh grouping field:
  none           → no grouping (org-wide)
  host.name      → agent.name
  source.ip      → data.srcip
  user.name      → data.dstuser
  file.hash.sha256 → data.sha256
  process.name   → data.audit.comm

Core fields (always available):
{core_fields}

{expanded_section}

Rules:
- Only use field_name values that exist in the Wazuh index mapping
- Conditions have field_name + operator + value only — no field_kind
- Prefer field values drawn from the expanded fields above when available
- For "same X seen across multiple different Y" detections (e.g. one user logging in from \
two or more different countries, or one host contacting many distinct destination IPs), set \
distinct_field (e.g. GeoLocation.country_name) and min_distinct (>= 2) on the leg, and pick a \
matching correlation_key (e.g. user.name). distinct_field must be aggregatable (not a free-text \
field) and must differ from the correlation key's field. Diversity requires a non-'none' correlation_key.
- If a current draft is provided, update it based on the latest instruction
- Return only valid JSON. No markdown, no code fences, no explanation outside the JSON.
"""


def build_rule_selection_prompt(grounding: dict) -> str:
    rule_catalog = grounding.get("rule_catalog", {})
    window_days = 7  # consistent with grounding builder default

    lines = []
    for rule_id, info in rule_catalog.items():
        desc = info.get("description", "")
        groups = ", ".join(info.get("groups", []))
        level = info.get("level", 0)
        seen = info.get("seen_count", 0)
        lines.append(f"  {rule_id}: level={level}, seen={seen}, groups=[{groups}], desc={desc}")

    catalog_text = "\n".join(lines) if lines else "  (no rules seen in recent data)"

    return _RULE_SELECTION_TEMPLATE.format(
        count=len(rule_catalog),
        window_days=window_days,
        catalog_text=catalog_text,
    )


def build_search_draft_prompt(grounding: dict) -> str:
    corr_keys = ", ".join(ck["value"] for ck in grounding.get("correlation_keys", []))
    severities = ", ".join(grounding.get("severities", []))

    core_parts = []
    for f in grounding.get("core_fields", []):
        field = f["value"]
        ftype = f["type"]
        core_parts.append(f"  {field} (type: {ftype})")
    core_fields_text = "\n".join(core_parts) if core_parts else "  (none)"

    expanded = grounding.get("expanded_fields", {})
    if expanded:
        exp_parts = []
        for field, info in expanded.items():
            ftype = info.get("type", "keyword")
            ops = info.get("operators", [])
            top_vals = info.get("top_values", [])
            vals_str = f", top values: {top_vals[:10]}" if top_vals else ""
            exp_parts.append(f"  {field} (type: {ftype}, operators: {ops}{vals_str})")
        expanded_section = "Expanded fields from selected rule.ids:\n" + "\n".join(exp_parts)
    else:
        expanded_section = "(no expanded fields — rely on core fields above)"

    return _SEARCH_DRAFT_TEMPLATE.format(
        corr_keys=corr_keys,
        severities=severities,
        core_fields=core_fields_text,
        expanded_section=expanded_section,
    )
