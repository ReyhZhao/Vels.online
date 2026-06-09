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

SYSTEM_PROMPT = """\
You are a senior security analyst. Given an incident context as JSON, triage the incident and \
return a structured assessment.

The input contains:
  source_kind   — the type of signal that generated this incident
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
  subject_recommendation   (string, optional) — best-matching incident subject slug, or omit if unclear. \
Choose from: phishing, malware, account_compromise, data_exfiltration, policy_violation

Return only valid JSON. No markdown, no code fences, no explanation.
"""

# Per-source preambles injected after the base prompt to guide source-specific reasoning.
_SOURCE_KIND_PREAMBLES = {
    "inbound_email": (
        "This incident was created from an email forwarded to the security team mailbox. "
        "The source_ref contains the raw email metadata: sender, subject, and body text. "
        "The email was sent TO the security mailbox as a report — it is not a direct attack payload. "
        "Treat the content as evidence of a potential phishing campaign, BEC attempt, or social "
        "engineering attempt unless it clearly indicates otherwise. "
        "Focus on the sender domain/IP reputation, the nature of any links or attachments, "
        "and whether the email matches known phishing patterns. "
        "The subject_recommendation for confirmed phishing is 'phishing'."
    ),
    "wazuh_event": (
        "This incident was triggered by a Wazuh SIEM alert from an endpoint agent. "
        "The source_ref contains the raw Wazuh rule data including rule_id, rule_description, "
        "and severity level. "
        "Focus on the rule category, the affected agent's behaviour, lateral movement indicators, "
        "and whether the alert pattern matches known false positive conditions for the rule."
    ),
    "vulnerability": (
        "This incident was created from a vulnerability scan finding. "
        "The source_ref contains CVE/vulnerability details including the affected component and "
        "CVSS score. "
        "Focus on exploitability in the context of the affected assets, patch or mitigation "
        "availability, asset exposure (internet-facing vs. internal), and the realistic risk "
        "to the organisation rather than the raw CVSS score alone."
    ),
    "agent_finding": (
        "This incident was raised by an automated security agent (e.g. a compliance or "
        "configuration check). "
        "The source_ref contains the agent's finding details. "
        "Focus on the policy or configuration gap identified, its exploitability, and the "
        "risk it poses relative to the asset's role and exposure."
    ),
}

TASK_SUMMARY_SYSTEM_PROMPT = """\
You are a security analyst reviewing the output of an automated security task. \
Given the task title and its raw console output, provide a concise structured assessment.

Return a JSON object with exactly these fields:
  summary   (string, required) — 2-3 sentence plain-language summary of what was done and the outcome
  findings  (array of strings, required) — list of notable findings, errors, or warnings; empty list if none
  status    (string, required) — one of: success, warning, error

Return only valid JSON. No markdown, no code fences, no explanation.
"""

CORRELATION_SYSTEM_PROMPT = """\
You are a senior security analyst specialising in threat intelligence correlation. \
Given a current incident and a list of recent incidents, identify which recent incidents \
are likely related to the current one based on:
  - Shared attack infrastructure (same IPs, domains, file hashes in IOCs)
  - Same or similar attack techniques or patterns
  - Same affected assets or asset groups
  - Temporal patterns suggesting coordinated or persistent threat activity

Return a JSON object with exactly these fields:
  related_incidents  (array, required) — list of objects, each with: \
id (integer), confidence (float 0.0-1.0), reason (string)
  correlation_summary  (string, required) — 1-2 sentences describing the overall correlation, \
or empty string if none found

Return only valid JSON. No markdown, no code fences, no explanation.
If no correlations are found return: {"related_incidents": [], "correlation_summary": ""}
"""


CLOSURE_MESSAGE_SYSTEM_PROMPT = """\
You are a security analyst writing a brief closure notification for a non-technical reporter who \
raised a security concern.

Given an incident context as JSON (title, severity, description, closure_reason, ai_triage_summaries), \
write a short plain-language message (2-4 sentences) suitable for sending by email.

The message should:
- Confirm the report was received and investigated
- Summarise what was found in plain language (no technical jargon)
- State whether it was resolved, found to be benign, or another outcome based on the closure_reason
- Be professional but accessible to a non-technical audience

Do NOT include a salutation or sign-off — just the body text.
Return only the message text. No JSON, no markdown, no code fences.
"""

RESIDUAL_GROUPING_SYSTEM_PROMPT = """\
You are a senior security analyst performing threat detection over a batch of unprocessed security alerts. \
Each alert has not been linked to an incident by any automated rule. \
Identify groups of alerts that together indicate suspicious or malicious activity — \
look for shared infrastructure, attack patterns, affected assets, or temporal clustering.

Input is a JSON array of alert objects, each with: id, title, severity, source_kind, entities (list of {type, value}).

Return a JSON object with exactly this field:
  groups  (array, required) — list of suspicious groupings, each with:
    alert_ids   (array of integers, required) — IDs of alerts in the group (minimum 2)
    rationale   (string, required) — 1-2 sentences explaining why these alerts are suspicious together
    confidence  (float, required) — probability 0.0-1.0 that this grouping represents real malicious activity

Return only valid JSON. No markdown, no code fences, no explanation.
If no suspicious groupings are found return: {"groups": []}
"""


def _build_system_prompt(source_kind: str = "", extra_context: str = "") -> str:
    parts = [SYSTEM_PROMPT]
    preamble = _SOURCE_KIND_PREAMBLES.get(source_kind, "")
    if preamble:
        parts.append("\n--- Source context ---\n" + preamble)
    if extra_context:
        parts.append("\n--- Organisation context ---\n" + extra_context)
    return "".join(parts)


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
            proposed_actions.append(ProposedAction(
                type="transition_state",
                label=item.get("label", f"Transition to {state}"),
                payload={"state": state},
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
        else:
            warnings.append(f"Unknown proposed action type '{action_type}'; skipped.")

    return AssistantResult(
        assistant_reply=reply,
        proposed_actions=proposed_actions,
        warnings=warnings,
    )


def _build_assistant_system_prompt(grounding: dict) -> str:
    incident = grounding.get("incident", {})
    available_templates = grounding.get("available_templates", [])
    allowed_transitions = grounding.get("allowed_transitions", [])
    field_allowlist = grounding.get("field_allowlist", [])
    contacts = grounding.get("contacts", [])

    template_lines = "\n".join(
        f'  - id={t["id"]}: "{t["name"]}" ({t["item_count"]} tasks)'
        for t in available_templates
    ) or "  (none)"

    contact_lines = "\n".join(
        f'  - id={c["id"]}: {c["name"]}'
        for c in contacts
    ) or "  (none attached)"

    return f"""\
You are a senior security analyst assistant helping a staff member investigate an incident.
You have full context about the incident below, and before answering you can look up related
incidents, alerts, and assets in the app and search the internet for threat intelligence. Any
findings from that research are included under INCIDENT CONTEXT as "research_notes" — use them in
your answer. If asked whether you can search the web or look things up, the answer is yes — you
already do so automatically as part of answering.
You may also propose specific actions the user can confirm with one click.

WORKING THE INCIDENT'S MANUAL TASKS:
The incident's tasks are listed under INCIDENT CONTEXT (each has an id, title, description,
task_type and state). When the analyst asks you to work, handle, or progress the tasks:
- Only work tasks whose task_type is "manual". For each, research what its description asks
  (use web search and the app lookups), then call add_task_comment(task_id, text) to record
  your findings as a staff-only note on that task.
- NEVER run, execute, or close a task yourself. You cannot run "automated" tasks (they launch
  jobs) or "wazuh_response" tasks (they act on live infrastructure) — if one of those should
  run, say so in your reply and let the analyst run it. Closing a completed task is always the
  analyst's decision; do not propose it as an action.
- If the wrong task template looks applied for this kind of incident, propose applying the
  correct one (apply_task_template); do not re-template silently.
- Work as many manual tasks as you can within this turn, then in your reply summarise which
  tasks you recorded findings for and which manual tasks still remain, so the analyst can ask
  you to continue.

=== INCIDENT CONTEXT ===
{json.dumps(grounding, indent=2)}

=== RESPONSE FORMAT ===
Return a JSON object with exactly these fields:
  assistant_reply   (string, required) — your conversational response; markdown is supported
  proposed_actions  (array, optional)  — zero or more actions the user can confirm

Each proposed action must be one of these shapes:

  Update an allowlisted field:
    {{"type": "update_field", "field": "<field>", "value": "<value>", "label": "<short human label>"}}
    Allowlisted fields: {', '.join(sorted(field_allowlist))}
    Valid severity values: critical, high, medium, low, info
    Valid tlp/pap values: white, green, amber, red
    For "subject": use the subject slug; for "assignee": use the username.

  Transition the incident state:
    {{"type": "transition_state", "state": "<target_state>", "label": "<short human label>"}}
    Currently allowed target states: {', '.join(allowed_transitions) or '(none — incident is closed)'}

  Apply a task template:
    {{"type": "apply_task_template", "template_id": <integer id>, "label": "<short human label>"}}
    Available templates for this incident's subject:
{template_lines}

  Add a comment to the incident:
    {{"type": "create_comment", "text": "<comment text>", "internal": <true|false>, "label": "<short human label>"}}
    Default to internal=true (staff-only note). Use internal=false only for org-visible comments.

  Send a message to an incident contact:
    {{"type": "send_contact_message", "contact_id": <integer id>, "message": "<message body>", "label": "<short human label>"}}
    The contact_id MUST be one of the contacts already attached to this incident:
{contact_lines}
    This is an externally visible action. Only propose it when there is a clear reason to notify a contact.

Rules:
- Only propose actions from the shapes above. Never invent action types.
- Only propose transitions to states in the allowed list above.
- Only propose templates from the available list above.
- Only propose field updates for fields in the allowlist above.
- Only propose send_contact_message with a contact_id from the list above.
- If no actions are warranted, return proposed_actions as [].
- Return only valid JSON. No markdown fences, no extra text.
"""


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

    def group_residual_alerts(self, alerts: list) -> ResidualGroupingResult:
        if not alerts:
            return ResidualGroupingResult(provider="gemini")
        prompt = json.dumps(alerts, indent=2)
        try:
            response = self._client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=RESIDUAL_GROUPING_SYSTEM_PROMPT,
                ),
            )
            text = response.text.strip()
        except Exception as exc:
            raise TriageError(f"Gemini residual grouping error: {exc}") from exc

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TriageError(f"Gemini returned non-JSON for residual grouping: {text[:200]}") from exc

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
    )
