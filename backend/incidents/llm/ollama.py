import json

import ollama
from django.conf import settings

from .base import BaseTriageProvider, CorrelationResult, TaskSummaryResult, TriageError, TriageResult
from .gemini import (
    CORRELATION_SYSTEM_PROMPT,
    TASK_SUMMARY_SYSTEM_PROMPT,
    _build_system_prompt,
    _parse_correlation_result,
    _parse_result,
    _parse_task_summary_result,
)


class OllamaTriageProvider(BaseTriageProvider):
    def __init__(self):
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = ollama.Client(host=base_url, headers=headers)
        self._model = getattr(settings, "OLLAMA_MODEL", "mistral")

    def triage_incident(self, payload: dict, extra_context: str = "") -> TriageResult:
        source_kind = payload.get("source_kind", "")
        prompt = json.dumps(payload, indent=2)
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _build_system_prompt(source_kind, extra_context)},
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

    def debug_triage_incident(self, system_prompt: str, user_prompt: str) -> tuple:
        """Run the LLM with provided prompts and return (raw_text, parsed_result_dict)."""
        from .gemini import _parse_result as _gr
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.message.content.strip()
        except Exception as exc:
            raise TriageError(f"Ollama API error: {exc}") from exc

        clean = text
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(lines[1:-1])

        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            data = {}

        result = _gr(data, provider="ollama")
        return text, {
            "severity_recommendation": result.severity_recommendation,
            "summary": result.summary,
            "primary_action": result.primary_action,
            "secondary_action": result.secondary_action,
            "false_positive_confidence": result.false_positive_confidence,
            "subject_recommendation": result.subject_recommendation,
        }

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

    def summarize_task_output(self, task_title: str, task_output: str) -> TaskSummaryResult:
        prompt = json.dumps({"task_title": task_title, "output": task_output[:8000]}, indent=2)
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": TASK_SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.message.content.strip()
        except Exception as exc:
            raise TriageError(f"Ollama task summary error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Ollama returned non-JSON for task summary: {text[:200]}") from exc

        return _parse_task_summary_result(data, provider="ollama")
