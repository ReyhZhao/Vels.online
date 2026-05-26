import json

import ollama
from django.conf import settings

from .base import BaseTriageProvider, CorrelationResult, TriageError, TriageResult
from .gemini import CORRELATION_SYSTEM_PROMPT, _build_system_prompt, _parse_correlation_result, _parse_result


class OllamaTriageProvider(BaseTriageProvider):
    def __init__(self):
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = ollama.Client(host=base_url, headers=headers)
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral")

    def triage_incident(self, payload: dict, extra_context: str = "") -> TriageResult:
        prompt = json.dumps(payload, indent=2)
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _build_system_prompt(extra_context)},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.message.content.strip()
        except Exception as exc:
            raise TriageError(f"Ollama API error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Ollama returned non-JSON: {text[:200]}") from exc

        return _parse_result(data, provider="ollama")

    def find_related_incidents(self, payload: dict, candidates: list) -> CorrelationResult:
        if not candidates:
            return CorrelationResult()
        prompt = json.dumps(
            {
                "current_incident": {
                    "title": payload.get("title"),
                    "assets": payload.get("assets", []),
                    "iocs": payload.get("iocs", []),
                    "severity": payload.get("severity"),
                },
                "recent_incidents": candidates,
            },
            indent=2,
        )
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": CORRELATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.message.content.strip()
        except Exception as exc:
            raise TriageError(f"Ollama correlation error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Ollama returned non-JSON for correlation: {text[:200]}") from exc

        return _parse_correlation_result(data)
