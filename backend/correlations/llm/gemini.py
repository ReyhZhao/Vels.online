import json

from django.conf import settings

from .base import BaseDraftProvider, DraftConfigError, DraftError, RuleDraftResult
from .search_prompt import build_rule_selection_prompt, build_search_draft_prompt

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


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        return "\n".join(lines[1:-1])
    return text


class GeminiDraftProvider(BaseDraftProvider):
    def __init__(self):
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise DraftConfigError(
                "GEMINI_API_KEY is not configured. "
                "Set the environment variable to enable the rule-author assistant."
            )
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=api_key)
        self._types = types

    def _build_contents(self, messages: list, current_draft=None):
        contents = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            text = msg.get("content", "")
            if current_draft and role == "user" and i == len(messages) - 1:
                text = f"{text}\n\nCurrent draft:\n{json.dumps(current_draft, indent=2)}"
            contents.append(
                self._types.Content(
                    role=role,
                    parts=[self._types.Part.from_text(text=text)],
                )
            )
        return contents

    def _generate(self, system_prompt: str, contents: list) -> str:
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            return response.text.strip()
        except Exception as exc:
            raise DraftError(f"Gemini API error: {exc}") from exc

    def _parse_json(self, raw: str, context: str) -> dict:
        raw = _strip_code_fence(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DraftError(f"Gemini returned non-JSON ({context}): {raw[:200]}") from exc

    def draft_rule(self, messages: list, grounding: dict, current_draft=None) -> RuleDraftResult:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._generate(_build_system_prompt(grounding), self._build_contents(messages, current_draft))
        data = self._parse_json(raw, "correlation draft")
        return RuleDraftResult(
            updated_draft=data.get("draft_rule") or {},
            assistant_reply=str(data.get("assistant_reply", "")),
            warnings=[],
        )

    def select_relevant_rule_ids(self, messages: list, grounding: dict) -> list:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._generate(build_rule_selection_prompt(grounding), self._build_contents(messages))
        data = self._parse_json(raw, "rule selection")
        return [str(r) for r in data.get("selected_rule_ids", []) if r]

    def draft_search_rule(self, messages: list, grounding: dict, current_draft=None) -> RuleDraftResult:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._generate(
            build_search_draft_prompt(grounding),
            self._build_contents(messages, current_draft),
        )
        data = self._parse_json(raw, "search draft")
        return RuleDraftResult(
            updated_draft=data.get("draft_rule") or {},
            assistant_reply=str(data.get("assistant_reply", "")),
            warnings=[],
        )
