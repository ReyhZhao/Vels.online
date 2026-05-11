import json

from django.conf import settings

from .base import BaseLLMProvider, ExceptionFields

SYSTEM_PROMPT = """\
You are a Wazuh security analyst. Given a Wazuh alert event as raw JSON, propose exception
rule fields that would suppress this alert when it is a false positive or expected behaviour.

Return a JSON object with exactly these fields (omit optional fields if not applicable):
  trigger_rule_id  (integer)          — Wazuh rule ID that fired the alert
  description      (string, required) — human-readable reason for the exception
  match_value      (string, optional) — value to match in the alert data
  field_name       (string, optional) — alert field to match against
  field_value      (string, optional) — expected value of that field
  field_type       (string, optional) — "pcre2" or "literal"
  agent_name       (string, optional) — agent to scope the exception to

Return only valid JSON. No markdown, no code fences, no explanation.
"""


class GeminiFlashProvider(BaseLLMProvider):
    def __init__(self):
        # Lazy import so the module can be imported without the package installed.
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )

    def generate_exception(self, source_ref: dict) -> ExceptionFields:
        prompt = json.dumps(source_ref, indent=2)
        response = self._model.generate_content(prompt)
        text = response.text.strip()
        # Strip markdown code fences if the model wraps the output anyway.
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        return ExceptionFields(
            trigger_rule_id=data.get("trigger_rule_id"),
            description=data.get("description", ""),
            match_value=data.get("match_value"),
            field_name=data.get("field_name"),
            field_value=data.get("field_value"),
            field_type=data.get("field_type"),
            agent_name=data.get("agent_name"),
        )
