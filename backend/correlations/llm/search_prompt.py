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


_SAMPLE_GEN_TEMPLATE = """\
You are a detection-engineering test-data assistant. Given a Scheduled Search Rule, \
generate synthetic raw Wazuh alert documents to TEST it.

The author wants {goal_text}.

Return a JSON object with exactly these fields:
  samples (array of objects, required) — synthetic raw Wazuh documents
  reasoning (string) — 1-2 sentence explanation

Rules for the documents:
- Each document is a partial raw Wazuh alert (a JSON object), shaped like the real samples below.
- Every document MUST include an "@timestamp" field (ISO-8601). For a should-fire test, put all \
documents within {window_minutes} minutes of each other.
- Only use field paths that exist in the field reference below; do not invent fields.
- Make the documents realistic — resemble genuine attack or benign logs, not just the rule's \
conditions echoed back.
- {goal_detail}
- Return only valid JSON. No markdown, no code fences, no explanation outside the JSON.

Rule under test:
{rule_text}

Field reference (paths you may use):
{fields_text}

Real example documents from this environment (for shape/realism):
{samples_text}
"""


def build_sample_gen_prompt(grounding: dict, expect_fire: bool) -> str:
    """System prompt for generating should-fire / should-not-fire Sample Documents."""
    rule = grounding.get("rule", {})
    window_minutes = rule.get("window_minutes", 60)

    if expect_fire:
        goal_text = "documents that SHOULD make the rule fire (a true-positive test)"
        goal_detail = (
            "Together, the documents must satisfy every leg of the rule for the same "
            "correlation key within the window (including any diversity constraint)."
        )
    else:
        goal_text = "documents that should NOT make the rule fire (a true-negative test)"
        goal_detail = (
            "The documents must fall just short — e.g. miss a leg, fall under a count "
            "threshold, sit outside the window, or lack the required diversity."
        )

    core = grounding.get("core_fields", [])
    expanded = grounding.get("expanded_fields", {})
    field_lines = [f"  {f['value']} (type: {f['type']})" for f in core]
    for field, info in expanded.items():
        field_lines.append(f"  {field} (type: {info.get('type', 'keyword')})")
    fields_text = "\n".join(field_lines) if field_lines else "  (none)"

    samples_text = json.dumps(grounding.get("sample_docs", [])[:5], indent=2) or "  (none)"
    rule_text = json.dumps(rule, indent=2)

    return _SAMPLE_GEN_TEMPLATE.format(
        goal_text=goal_text,
        goal_detail=goal_detail,
        window_minutes=window_minutes,
        rule_text=rule_text,
        fields_text=fields_text,
        samples_text=samples_text,
    )


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
