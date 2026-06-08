import json

import ollama
from django.conf import settings

from .base import BaseLLMProvider, ExceptionFields
from .gemini import SYSTEM_PROMPT


class OllamaProvider(BaseLLMProvider):
    def __init__(self):
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        timeout = getattr(settings, "OLLAMA_TIMEOUT_S", 60.0)
        self._client = ollama.Client(host=base_url, headers=headers, timeout=timeout)
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral")

    def generate_exception(self, source_ref: dict) -> ExceptionFields:
        prompt = json.dumps(source_ref, indent=2)
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            format="json",
        )
        text = response.message.content.strip()
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
