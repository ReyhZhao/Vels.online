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
draft a Scheduled Search Rule that periodically queries raw Wazuh alert events in OpenSearch. \
You can search the internet for threat intelligence to inform the rule; any findings are included \
below under "Internet research gathered for this request". If asked whether you can look things up \
online, the answer is yes.

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
  "baseline_lookback_days": integer (min 1, default 30) — Novelty Constraint history depth: how far back to look when deciding a value is "new". Larger values approach "first time ever". Only relevant when a leg sets novelty_field,
  "max_findings_per_run": integer (min 1, default 50),
  "severity": "string — one of: {severities}",
  "enabled": true,
  "time_window_start": "string 'HH:MM' or null — OPTIONAL rule-level time-of-day window start, in the organisation's local time",
  "time_window_end": "string 'HH:MM' or null — window end; may be EARLIER than start to express a window crossing midnight (e.g. 22:00–06:00)",
  "time_window_days": "array of integers 1-7 — ISO weekdays the window applies to (1=Mon … 7=Sun); empty array for no window",
  "time_window_mode": "string — 'inside' (consider only docs INSIDE the window) or 'outside' (consider only docs OUTSIDE the window)",
  "legs": [
    {{
      "count": integer (min 1) — the matched-document threshold this leg compares against,
      "count_operator": "string (optional, default 'gte') — how count is compared with the matched-doc count: 'gte' (at least N, the normal case) or 'lte' (Absence Firing: AT MOST N matched, e.g. count 0 + lte = 'no matching documents in the window'). Only 'gte' or 'lte'.",
      "display_order": integer — 0-indexed position,
      "distinct_field": "string (optional) — Diversity Constraint: an aggregatable Wazuh field. The leg fires only when its matches span at least min_distinct DISTINCT values of this field for the same correlation key. Leave empty for no constraint.",
      "min_distinct": integer (min 2, default 2) — required when distinct_field is set,
      "novelty_field": "string (optional) — Novelty Constraint: an aggregatable Wazuh field. The leg fires only when this field takes a value NEVER SEEN BEFORE for the correlation key within baseline_lookback_days (first-seen detection, e.g. a user logging onto a host new for them). Leave empty for no constraint.",
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
- For "first time X" / first-seen detections (e.g. a user logging onto a host they have NEVER \
used before, a new process on a host), set novelty_field (e.g. agent.name) on the leg and pick a \
matching correlation_key (e.g. user.name), then set baseline_lookback_days for the history depth \
(e.g. 30–90 days). A value is "new" when its earliest sighting within the baseline falls in the \
most recent run interval. novelty_field must be aggregatable, must differ from the correlation \
key's field, requires a non-'none' correlation_key, and CANNOT be combined with the absence \
(count ≤) operator. Novelty is distinct from Diversity: Diversity counts distinct values WITHIN \
one window; Novelty fires on a value not seen in the baseline history at all.
- For "absence" / "nothing happened" detections (e.g. a heartbeat or expected event that did NOT \
arrive — "no successful backup in the last 24h", "agent stopped reporting", "no logins from the \
service account"), set count_operator='lte' on the leg and use count to express the ceiling (count=0 \
for "no matching documents at all"). The absence (lte) operator requires correlation_key='none' \
(org-wide) and CANNOT be combined with a novelty_field. Leave count_operator at 'gte' for every \
ordinary "this happened N times" rule.
- Time-of-day window (OPTIONAL): only set time_window_start, time_window_end, and a non-empty \
time_window_days when the user asks to restrict detection to (or away from) particular hours/days — \
e.g. "only outside working hours", "only at night", "only on weekends", "during business hours". \
Use time_window_mode='outside' for "outside/off-hours/after-hours" phrasing and 'inside' for \
"during/only between". Times are the organisation's LOCAL time. To express a window that crosses \
midnight (e.g. 22:00 to 06:00) set time_window_end earlier than time_window_start. If the user does \
NOT mention timing, leave time_window_start and time_window_end null, time_window_days empty, and \
time_window_mode 'inside' (no constraint). A window needs BOTH start and end and at least one day.
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
- Every document MUST include an "@timestamp" field. Use either ISO-8601 (e.g. \
2026-06-15T10:00:00Z) or a relative offset resolved at run time: now, now-40d, now-2m, now+1h \
(units s/m/h/d/w). Relative offsets are the reliable way to place a document in a specific era.
- {goal_detail}
- Only use field paths that exist in the field reference below; do not invent fields.
- Make the documents realistic — resemble genuine attack or benign logs, not just the rule's \
conditions echoed back.
- Return only valid JSON. No markdown, no code fences, no explanation outside the JSON.

Rule under test:
{rule_text}

Field reference (paths you may use):
{fields_text}

Real example documents from this environment (for shape/realism):
{samples_text}
"""


def _sample_goal_detail(rule: dict, expect_fire: bool) -> str:
    """Per-mode 'how to shape the docs' instruction, aware of the novelty/absence axes.

    The default (count/diversity) keeps all docs inside one window; a Novelty Constraint
    instead needs two *eras* (a baseline that establishes known values + a recent doc with a
    new value), and an Absence Firing needs the matching set to be empty (fire) or full (no-fire).
    """
    legs = rule.get("legs", []) or []
    window = rule.get("window_minutes", 60)
    interval = rule.get("interval_minutes", 60)
    baseline = rule.get("baseline_lookback_days", 30)
    novelty_field = next((l.get("novelty_field") for l in legs if (l.get("novelty_field") or "")), None)
    has_absence = any(l.get("count_operator") == "lte" for l in legs)
    baseline_offset = max(1, baseline // 2)

    if novelty_field:
        if expect_fire:
            return (
                f"This rule has a NOVELTY (first-seen) constraint on '{novelty_field}'. Stage TWO eras "
                f"using relative @timestamp offsets: (1) one or more BASELINE docs older than the last "
                f"{interval} minutes but within {baseline} days (e.g. @timestamp now-{baseline_offset}d) that "
                f"establish KNOWN values of '{novelty_field}' for the correlation key; and (2) at least one "
                f"DETECTION doc within the last {interval} minutes (e.g. @timestamp now-2m) whose "
                f"'{novelty_field}' value is BRAND NEW for that correlation key (it must NOT appear in any "
                f"baseline doc). Every doc must still satisfy the leg's conditions."
            )
        return (
            f"This rule has a NOVELTY (first-seen) constraint on '{novelty_field}'. To NOT fire, the recent "
            f"document's '{novelty_field}' value must already be KNOWN: include a BASELINE doc (e.g. @timestamp "
            f"now-{baseline_offset}d) carrying the SAME '{novelty_field}' value (for the same correlation key) as a "
            f"recent doc (e.g. @timestamp now-2m), so nothing is new within the last {interval} minutes."
        )

    if has_absence:
        if expect_fire:
            return (
                f"This is an ABSENCE firing (count ≤ threshold). To fire, the window must contain NO documents "
                f"matching the leg's conditions — generate only NON-matching docs within the last {window} minutes "
                f"(e.g. @timestamp now-5m), or return an empty list."
            )
        return (
            f"This is an ABSENCE rule. To NOT fire, generate enough MATCHING documents within the last {window} "
            f"minutes (e.g. @timestamp now-5m) to exceed the leg's threshold."
        )

    if expect_fire:
        return (
            f"Together, the documents must satisfy every leg of the rule for the same correlation key within "
            f"{window} minutes of each other (e.g. @timestamp now-5m), including any diversity constraint."
        )
    return (
        "The documents must fall just short — e.g. miss a leg, fall under a count threshold, sit outside "
        "the window, or lack the required diversity."
    )


def build_sample_gen_prompt(grounding: dict, expect_fire: bool) -> str:
    """System prompt for generating should-fire / should-not-fire Sample Documents."""
    rule = grounding.get("rule", {})

    if expect_fire:
        goal_text = "documents that SHOULD make the rule fire (a true-positive test)"
    else:
        goal_text = "documents that should NOT make the rule fire (a true-negative test)"
    goal_detail = _sample_goal_detail(rule, expect_fire)

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

    draft = _SEARCH_DRAFT_TEMPLATE.format(
        corr_keys=corr_keys,
        severities=severities,
        core_fields=core_fields_text,
        expanded_section=expanded_section,
    )
    research = grounding.get("research_notes")
    if research:
        draft += f"\n\n--- Internet research gathered for this request ---\n{research}\n"
    return draft
