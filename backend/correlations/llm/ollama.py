import json

from django.conf import settings

from .base import BaseDraftProvider, DraftError, RuleDraftResult
from .gemini import _build_system_prompt, _strip_code_fence


class OllamaDraftProvider(BaseDraftProvider):
    def __init__(self):
        import ollama
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = ollama.Client(host=base_url, headers=headers)
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral")

    def draft_rule(self, messages: list, grounding: dict, current_draft=None) -> RuleDraftResult:
        if not messages:
            raise DraftError("No messages provided.")

        system_prompt = _build_system_prompt(grounding)

        ollama_messages = [{"role": "system", "content": system_prompt}]
        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if current_draft and role == "user" and i == len(messages) - 1:
                text = f"{text}\n\nCurrent draft:\n{json.dumps(current_draft, indent=2)}"
            ollama_messages.append({"role": role, "content": text})

        try:
            response = self._client.chat(model=self._model, messages=ollama_messages)
            raw = response.message.content.strip()
        except Exception as exc:
            raise DraftError(f"Ollama API error: {exc}") from exc

        raw = _strip_code_fence(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DraftError(f"Ollama returned non-JSON: {raw[:200]}") from exc

        return RuleDraftResult(
            updated_draft=data.get("draft_rule") or {},
            assistant_reply=str(data.get("assistant_reply", "")),
            warnings=[],
        )
