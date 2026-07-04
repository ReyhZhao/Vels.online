import json

from django.conf import settings

from .base import BaseDraftProvider, DraftConfigError, DraftError, RuleDraftResult
from .prompts import _SYSTEM_PROMPT_TEMPLATE, _build_system_prompt
from .search_prompt import build_rule_selection_prompt, build_search_draft_prompt


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

    # ── agentic loop (ADR-0011) ──────────────────────────────────────────────
    def uses_native_web_search(self) -> bool:
        return True

    def chat(self, messages: list, tools: list):
        from assistants.providers import gemini_chat
        system = ""
        rest = []
        for m in messages:
            if m.get("role") == "system" and not system:
                system = m.get("content", "")
            else:
                rest.append(m)
        return gemini_chat(
            self._client, self._types, settings.GEMINI_MODEL,
            system, rest, tools, with_grounding=True,
        )

    def generate_sample_docs(self, grounding: dict, expect_fire: bool) -> list:
        from .search_prompt import build_sample_gen_prompt
        instruction = "Generate the sample documents now."
        raw = self._generate(
            build_sample_gen_prompt(grounding, expect_fire),
            self._build_contents([{"role": "user", "content": instruction}]),
        )
        data = self._parse_json(raw, "sample generation")
        samples = data.get("samples", [])
        return samples if isinstance(samples, list) else []
