import json
from typing import Optional

from django.conf import settings

from .base import (
    ASSISTANT_FIELD_ALLOWLIST,
    AssistantError,
    AssistantResult,
    BaseTriageProvider,
    CorrelationResult,
    ProposedAction,
    ResidualGroup,
    ResidualGroupingResult,
    TaskSummaryResult,
    TriageConfigError,
    TriageError,
    TriageResult,
    VALID_ACTIONS,
)

from .prompts import (
    CLOSURE_MESSAGE_SYSTEM_PROMPT,
    CORRELATION_SYSTEM_PROMPT,
    LESSON_DISTILL_SYSTEM_PROMPT,
    REPORT_SUMMARY_SYSTEM_PROMPT,
    SCAN_NEIGHBOURHOOD_SYSTEM_PROMPT,
    SEARCH_SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TASK_SUMMARY_SYSTEM_PROMPT,
    _build_assistant_system_prompt,
    _build_system_prompt,
)


def _strip_code_fence_if_present(text: str) -> str:
    """Remove a single leading/trailing markdown code fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    return stripped


def _first_balanced_json_object(text: str) -> Optional[str]:
    """Return the first balanced top-level ``{...}`` substring, or None.

    Walks the string tracking brace depth (and skipping braces inside JSON strings)
    so a JSON object embedded in prose can be recovered even when the model wraps
    the envelope in reasoning text.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort parse of a JSON object from model output that may wrap it in prose.

    Tries the whole (fence-stripped) string first, then falls back to the first
    balanced ``{...}`` object. Returns a dict, or None if nothing parseable is found.
    """
    stripped = _strip_code_fence_if_present(text)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    candidate = _first_balanced_json_object(stripped)
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# Used when the model returns no recoverable JSON envelope but the output looks like a
# failed JSON/reasoning attempt — we must never surface that raw blob to the analyst.
_ASSISTANT_FALLBACK_REPLY = (
    "I couldn't produce a structured response for this incident just now. "
    "Please rephrase your request or try again."
)


def _parse_assistant_envelope(raw: str, grounding: dict) -> AssistantResult:
    """Turn raw model output into an AssistantResult.

    Shared by all providers so behaviour stays consistent: recovers a JSON envelope
    even when the model wraps it in prose, and on genuine failure never echoes the
    model's reasoning preamble or a literal JSON blob back to the analyst.
    """
    data = _extract_json_object(raw)
    if data is not None:
        return _parse_assistant_result(data, grounding)

    stripped = _strip_code_fence_if_present(raw)
    # If the output contains a brace it was a failed JSON/reasoning attempt — don't dump it.
    if "{" in stripped:
        return AssistantResult(
            assistant_reply=_ASSISTANT_FALLBACK_REPLY,
            proposed_actions=[],
            warnings=["Provider did not return the expected JSON envelope; proposed actions are unavailable."],
        )
    # Genuine plain-text answer — safe to surface as the reply.
    return AssistantResult(
        assistant_reply=stripped,
        proposed_actions=[],
        warnings=["Provider returned plain text instead of the expected JSON envelope; proposed actions are unavailable."],
    )


def _parse_assistant_result(data: dict, grounding: dict) -> AssistantResult:
    """Validate a parsed assistant JSON payload against the grounding and build an AssistantResult.

    Shared by all providers so action validation stays consistent regardless of the LLM backend.
    """
    reply = str(data.get("assistant_reply", ""))
    raw_actions = data.get("proposed_actions") or []
    proposed_actions = []
    warnings = []

    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action_type = item.get("type", "")
        if action_type == "update_field":
            field_name = item.get("field", "")
            if field_name not in ASSISTANT_FIELD_ALLOWLIST:
                warnings.append(f"Proposed field '{field_name}' is not in the allowlist; skipped.")
                continue
            proposed_actions.append(ProposedAction(
                type="update_field",
                label=item.get("label", f"Update {field_name}"),
                payload={"field": field_name, "value": item.get("value")},
            ))
        elif action_type == "transition_state":
            state = item.get("state", "")
            allowed = grounding.get("allowed_transitions", [])
            if state not in allowed:
                warnings.append(f"Proposed transition to '{state}' is not allowed from current state; skipped.")
                continue
            payload = {"state": state}
            # Closing requires a structured closure reason (the transition service
            # rejects a close without one); for a duplicate it also needs the
            # canonical incident reference. Validate here so an invalid close is
            # dropped with a warning rather than presented as a doomed action.
            if state == "closed":
                closure_reason = item.get("closure_reason")
                valid_reasons = grounding.get("closure_reasons", [])
                if closure_reason not in valid_reasons:
                    warnings.append(
                        f"Proposed close has missing/invalid closure_reason {closure_reason!r}; skipped."
                    )
                    continue
                payload["closure_reason"] = closure_reason
                if closure_reason == "duplicate":
                    duplicate_of = item.get("duplicate_of")
                    if not duplicate_of:
                        warnings.append(
                            "Proposed close-as-duplicate is missing the canonical incident reference (duplicate_of); skipped."
                        )
                        continue
                    payload["duplicate_of"] = duplicate_of
            proposed_actions.append(ProposedAction(
                type="transition_state",
                label=item.get("label", f"Transition to {state}"),
                payload=payload,
            ))
        elif action_type == "apply_task_template":
            template_id = item.get("template_id")
            available_ids = {t["id"] for t in grounding.get("available_templates", [])}
            if template_id not in available_ids:
                warnings.append(f"Proposed template id {template_id} is not available for this incident; skipped.")
                continue
            template_name = next(
                (t["name"] for t in grounding.get("available_templates", []) if t["id"] == template_id),
                str(template_id),
            )
            proposed_actions.append(ProposedAction(
                type="apply_task_template",
                label=item.get("label", f"Apply template '{template_name}'"),
                payload={"template_id": template_id, "template_name": template_name},
            ))
        elif action_type == "create_comment":
            text = (item.get("text") or "").strip()
            if not text:
                warnings.append("Proposed create_comment has empty text; skipped.")
                continue
            internal = item.get("internal")
            if internal is None:
                internal = True
            proposed_actions.append(ProposedAction(
                type="create_comment",
                label=item.get("label", "Add comment"),
                payload={"text": text, "internal": bool(internal)},
            ))
        elif action_type == "send_contact_message":
            contact_id = item.get("contact_id")
            valid_contact_ids = {c["id"] for c in grounding.get("contacts", [])}
            if contact_id not in valid_contact_ids:
                warnings.append(
                    f"Proposed send_contact_message contact_id {contact_id!r} is not attached to this incident; skipped."
                )
                continue
            message = (item.get("message") or "").strip()
            if not message:
                warnings.append("Proposed send_contact_message has empty message; skipped.")
                continue
            contact_name = next(
                (c["name"] for c in grounding.get("contacts", []) if c["id"] == contact_id),
                str(contact_id),
            )
            proposed_actions.append(ProposedAction(
                type="send_contact_message",
                label=item.get("label", f"Send message to {contact_name}"),
                payload={"contact_id": contact_id, "message": message, "contact_name": contact_name},
            ))
        elif action_type == "propose_generate_report":
            template_id = item.get("template_id")
            available = grounding.get("available_report_templates", [])
            available_ids = {t["id"] for t in available}
            if template_id not in available_ids:
                warnings.append(
                    f"Proposed report template id {template_id!r} is not available; skipped."
                )
                continue
            tmpl = next((t for t in available if t["id"] == template_id), None)
            proposed_actions.append(ProposedAction(
                type="propose_generate_report",
                label=item.get("label", f"Generate report '{tmpl['name']}'"),
                payload={
                    "template_id": template_id,
                    "template_name": tmpl["name"],
                    "audience": tmpl["audience"],
                },
            ))
        else:
            warnings.append(f"Unknown proposed action type '{action_type}'; skipped.")

    return AssistantResult(
        assistant_reply=reply,
        proposed_actions=proposed_actions,
        warnings=warnings,
    )


class GeminiTriageProvider(BaseTriageProvider):
    def __init__(self):
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise TriageConfigError(
                "GEMINI_API_KEY is not configured. Set the environment variable to enable AI triage."
            )
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=api_key)
        self._types = types

    def triage_incident(self, payload: dict, extra_context: str = "") -> TriageResult:
        source_kind = payload.get("source_kind", "")
        prompt = json.dumps(payload, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=_build_system_prompt(source_kind, extra_context),
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

    def debug_triage_incident(self, system_prompt: str, user_prompt: str) -> tuple:
        """Run the LLM with provided prompts and return (raw_text, parsed_result_dict)."""
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini API error: {exc}") from exc

        clean = text
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(lines[1:-1])

        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            data = {}

        result = _parse_result(data, provider="gemini")
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
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=CORRELATION_SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini correlation error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON for correlation: {text[:200]}") from exc

        return _parse_correlation_result(data)

    def scan_neighbourhood(self, residual_alerts: list, context_alerts: list) -> ResidualGroupingResult:
        if not residual_alerts:
            return ResidualGroupingResult(provider="gemini")
        prompt = json.dumps(
            {"residual_alerts": residual_alerts, "context_alerts": context_alerts}, indent=2
        )
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=SCAN_NEIGHBOURHOOD_SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini neighbourhood scan error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON for neighbourhood scan: {text[:200]}") from exc

        return _parse_residual_grouping_result(data)

    def summarize_task_output(self, task_title: str, task_output: str) -> TaskSummaryResult:
        prompt = json.dumps({"task_title": task_title, "output": task_output[:8000]}, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=TASK_SUMMARY_SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini task summary error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON for task summary: {text[:200]}") from exc

        return _parse_task_summary_result(data, provider="gemini")

    def distill_triage_lesson(self, payload: dict) -> dict:
        prompt = json.dumps(payload, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=LESSON_DISTILL_SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini lesson distillation error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON for lesson distillation: {text[:200]}") from exc

        return _parse_distilled_lesson(data)

    # ── agentic loop (ADR-0011) ──────────────────────────────────────────────
    def uses_native_web_search(self) -> bool:
        return True

    def supports_complex_tools(self) -> bool:
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

    def assist_incident(self, messages: list, grounding: dict) -> AssistantResult:
        if not messages:
            raise AssistantError("No messages provided.")

        system_prompt = _build_assistant_system_prompt(grounding)

        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            contents.append(
                self._types.Content(
                    role=role,
                    parts=[self._types.Part.from_text(text=str(msg.get("content", "")))],
                )
            )

        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text.strip()
        except Exception as exc:
            raise AssistantError(f"Gemini API error: {exc}") from exc

        if not raw:
            raise AssistantError("Gemini returned an empty response.")

        return _parse_assistant_envelope(raw, grounding)

    def generate_closure_message(self, incident_context: dict) -> str:
        prompt = json.dumps(incident_context, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=CLOSURE_MESSAGE_SYSTEM_PROMPT,
                ),
            )
            return response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini closure message error: {exc}") from exc

    def generate_report_summary(self, grounding: dict) -> str:
        prompt = json.dumps(grounding, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=REPORT_SUMMARY_SYSTEM_PROMPT,
                ),
            )
            return response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini report summary error: {exc}") from exc

    def generate_search_incident_summary(self, evidence: dict) -> str:
        prompt = json.dumps(evidence, indent=2, default=str)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=SEARCH_SUMMARY_SYSTEM_PROMPT,
                ),
            )
            return response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini search summary error: {exc}") from exc


def _parse_residual_grouping_result(data: dict) -> ResidualGroupingResult:
    groups = []
    for item in data.get("groups", []):
        if not isinstance(item, dict):
            continue
        alert_ids = []
        for aid in item.get("alert_ids", []):
            try:
                alert_ids.append(int(aid))
            except (ValueError, TypeError):
                pass
        if len(alert_ids) < 2:
            continue
        confidence = float(item.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        rationale = item.get("rationale", "") or ""
        groups.append(ResidualGroup(alert_ids=alert_ids, rationale=str(rationale), confidence=confidence))
    return ResidualGroupingResult(groups=groups, provider="gemini")


def _parse_task_summary_result(data: dict, provider: str) -> TaskSummaryResult:
    summary = data.get("summary", "") or ""
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    findings = [str(f) for f in findings if f]
    status = data.get("status", "success")
    if status not in ("success", "warning", "error"):
        status = "success"
    return TaskSummaryResult(summary=summary, findings=findings, status=status, provider=provider)


def _parse_distilled_lesson(data: dict) -> dict:
    """Normalise a distiller response to the ``{"guidance", "selector"}`` contract.

    Only these two keys are meaningful downstream; anything else the model returns is
    dropped. Non-string values degrade to empty so a malformed response proposes nothing
    rather than raising. Shared by the Gemini and Ollama providers.
    """
    if not isinstance(data, dict):
        return {"guidance": "", "selector": ""}
    guidance = data.get("guidance", "")
    selector = data.get("selector", "")
    return {
        "guidance": guidance.strip() if isinstance(guidance, str) else "",
        "selector": selector.strip() if isinstance(selector, str) else "",
    }


def _parse_correlation_result(data: dict) -> CorrelationResult:
    related = data.get("related_incidents", [])
    summary = data.get("correlation_summary", "") or ""
    related_ids = []
    max_confidence = 0.0
    for item in related:
        if not isinstance(item, dict):
            continue
        confidence = float(item.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        if confidence > max_confidence:
            max_confidence = confidence
        inc_id = item.get("id")
        if inc_id is not None:
            try:
                related_ids.append(int(inc_id))
            except (ValueError, TypeError):
                pass
    return CorrelationResult(
        related_incident_ids=related_ids,
        correlation_summary=summary if isinstance(summary, str) else "",
        max_confidence=max_confidence,
    )


VALID_SUBJECT_SLUGS = {"phishing", "malware", "account_compromise", "data_exfiltration", "policy_violation"}


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

    disposition = _clamp_unit(data.get("disposition_confidence", 0.0))

    subject_recommendation = data.get("subject_recommendation")
    if subject_recommendation and subject_recommendation not in VALID_SUBJECT_SLUGS:
        subject_recommendation = None

    return TriageResult(
        severity_recommendation=severity,
        summary=data.get("summary", ""),
        primary_action=primary,
        secondary_action=secondary,
        false_positive_confidence=confidence,
        provider=provider,
        subject_recommendation=subject_recommendation,
        disposition_confidence=disposition,
    )


def _clamp_unit(value) -> float:
    """Coerce a model-supplied value to a float in [0.0, 1.0], defaulting to 0.0."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
