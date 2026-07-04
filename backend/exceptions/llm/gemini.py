import json

from django.conf import settings

from .base import BaseLLMProvider, ExceptionFields
from .prompts import SYSTEM_PROMPT


class GeminiFlashProvider(BaseLLMProvider):
    def __init__(self):
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._types = types

    def generate_exception(self, source_ref: dict) -> ExceptionFields:
        prompt = json.dumps(source_ref, indent=2)
        response = self._client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        text = response.text.strip()
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
