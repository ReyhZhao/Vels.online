import json

from django.conf import settings

from .base import BaseDraftProvider, DraftError, RuleDraftResult
from .gemini import _build_system_prompt, _strip_code_fence
from .search_prompt import build_rule_selection_prompt, build_search_draft_prompt


class OllamaDraftProvider(BaseDraftProvider):
    def __init__(self):
        import ollama
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = ollama.Client(host=base_url, headers=headers)
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral")

    def _chat(self, system_prompt: str, messages: list, current_draft=None) -> str:
        ollama_messages = [{"role": "system", "content": system_prompt}]
        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if current_draft and role == "user" and i == len(messages) - 1:
                text = f"{text}\n\nCurrent draft:\n{json.dumps(current_draft, indent=2)}"
            ollama_messages.append({"role": role, "content": text})

        try:
            response = self._client.chat(model=self._model, messages=ollama_messages)
            return response.message.content.strip()
        except Exception as exc:
            raise DraftError(f"Ollama API error: {exc}") from exc

    def _parse_json(self, raw: str, context: str) -> dict:
        raw = _strip_code_fence(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DraftError(f"Ollama returned non-JSON ({context}): {raw[:200]}") from exc

    def draft_rule(self, messages: list, grounding: dict, current_draft=None) -> RuleDraftResult:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._chat(_build_system_prompt(grounding), messages, current_draft)
        data = self._parse_json(raw, "correlation draft")
        return RuleDraftResult(
            updated_draft=data.get("draft_rule") or {},
            assistant_reply=str(data.get("assistant_reply", "")),
            warnings=[],
        )

    def select_relevant_rule_ids(self, messages: list, grounding: dict) -> list:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._chat(build_rule_selection_prompt(grounding), messages)
        data = self._parse_json(raw, "rule selection")
        return [str(r) for r in data.get("selected_rule_ids", []) if r]

    def draft_search_rule(self, messages: list, grounding: dict, current_draft=None) -> RuleDraftResult:
        if not messages:
            raise DraftError("No messages provided.")
        raw = self._chat(build_search_draft_prompt(grounding), messages, current_draft)
        data = self._parse_json(raw, "search draft")
        return RuleDraftResult(
            updated_draft=data.get("draft_rule") or {},
            assistant_reply=str(data.get("assistant_reply", "")),
            warnings=[],
        )
