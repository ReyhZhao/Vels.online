import json

from django.conf import settings

from .base import BaseTriageProvider, CorrelationResult, TaskSummaryResult, TriageConfigError, TriageError, TriageResult, VALID_ACTIONS

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


def _build_system_prompt(source_kind: str = "", extra_context: str = "") -> str:
    parts = [SYSTEM_PROMPT]
    preamble = _SOURCE_KIND_PREAMBLES.get(source_kind, "")
    if preamble:
        parts.append("\n--- Source context ---\n" + preamble)
    if extra_context:
        parts.append("\n--- Organisation context ---\n" + extra_context)
    return "".join(parts)


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
