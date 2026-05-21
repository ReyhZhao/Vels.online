import json

from django.conf import settings

from .base import BaseTriageProvider, TriageError, TriageResult, VALID_ACTIONS

SYSTEM_PROMPT = """\
You are a senior security analyst. Given an incident context as JSON, triage the incident and \
return a structured assessment.

The input contains:
  source_ref    — raw event data (Wazuh alert, vulnerability scan, etc.)
  assets        — list of affected assets with name, kind, agent_name, ip_address
  iocs          — extracted indicators of compromise (IPs, domains, URLs)
  title         — incident title
  description   — incident description
  severity      — current system-assigned severity

Return a JSON object with exactly these fields:
  severity_recommendation  (string, required) — one of: critical, high, medium, low, info
  summary                  (string, required) — 2-3 sentence plain-language explanation of the assessment
  primary_action           (string, required) — one of: escalate, create_exception, assign_to_analyst, \
close_as_false_positive, monitor, close_as_informational
  secondary_action         (string, optional) — same choices as primary_action, or omit
  false_positive_confidence (float, required) — probability 0.0-1.0 that this is a false positive

Return only valid JSON. No markdown, no code fences, no explanation.
"""


class GeminiTriageProvider(BaseTriageProvider):
    def __init__(self):
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._types = types

    def triage_incident(self, payload: dict) -> TriageResult:
        prompt = json.dumps(payload, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini API error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON: {text[:200]}") from exc

        return _parse_result(data, provider="gemini")


def _parse_result(data: dict, provider: str) -> TriageResult:
    severity = data.get("severity_recommendation", "medium")
    if severity not in ("critical", "high", "medium", "low", "info"):
        severity = "medium"

    primary = data.get("primary_action", "assign_to_analyst")
    if primary not in VALID_ACTIONS:
        primary = "assign_to_analyst"

    secondary = data.get("secondary_action")
    if secondary and secondary not in VALID_ACTIONS:
        secondary = None

    confidence = float(data.get("false_positive_confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    return TriageResult(
        severity_recommendation=severity,
        summary=data.get("summary", ""),
        primary_action=primary,
        secondary_action=secondary,
        false_positive_confidence=confidence,
        provider=provider,
    )
