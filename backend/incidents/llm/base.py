from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Fields the incident assistant is allowed to propose updating.
ASSISTANT_FIELD_ALLOWLIST = {"severity", "tlp", "pap", "description", "subject", "assignee"}

VALID_ACTIONS = {
    "escalate",
    "create_exception",
    "assign_to_analyst",
    "close_as_false_positive",
    "monitor",
    "close_as_informational",
}

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
RANK_TO_SEV = {v: k for k, v in SEVERITY_RANK.items()}


class TriageError(Exception):
    """Raised when the LLM returns an unparseable or invalid triage response."""


class TriageConfigError(Exception):
    """Raised when the triage provider is misconfigured (missing API key, etc.).
    This error is not retriable — retrying will not fix a config problem."""


@dataclass
class TriageResult:
    severity_recommendation: str
    summary: str
    primary_action: str
    secondary_action: Optional[str] = None
    false_positive_confidence: float = 0.0
    provider: str = ""
    subject_recommendation: Optional[str] = None
    # Positive "this incident is real AND correctly classified" confidence — the
    # signal the agentic Triage Work phase gates on (ADR-0024). Distinct from, and
    # not the inverse of, false_positive_confidence: an incident can be low-FP
    # (clearly not junk) yet low-disposition (ambiguous which subject/severity).
    disposition_confidence: float = 0.0


@dataclass
class CorrelationResult:
    related_incident_ids: List[int] = field(default_factory=list)
    correlation_summary: str = ""
    max_confidence: float = 0.0


@dataclass
class TaskSummaryResult:
    summary: str = ""
    findings: List[str] = field(default_factory=list)
    status: str = "success"
    provider: str = ""


@dataclass
class ResidualGroup:
    alert_ids: List[int] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0


@dataclass
class ResidualGroupingResult:
    groups: List[ResidualGroup] = field(default_factory=list)
    provider: str = ""


class AssistantError(Exception):
    """Raised when the LLM returns an unparseable or invalid assistant response."""


class AssistantConfigError(Exception):
    """Raised when the assistant provider is misconfigured. Not retriable."""


@dataclass
class ProposedAction:
    type: str
    label: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantResult:
    assistant_reply: str = ""
    proposed_actions: List[ProposedAction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BaseTriageProvider(ABC):
    @abstractmethod
    def triage_incident(self, payload: dict, extra_context: str = "") -> TriageResult:
        """Analyse an incident payload and return a triage assessment."""

    def find_related_incidents(self, payload: dict, candidates: list) -> CorrelationResult:
        """Check for correlations with recent incidents. Override in providers that support it."""
        return CorrelationResult()

    def summarize_task_output(self, task_title: str, task_output: str) -> TaskSummaryResult:
        """Parse and summarise automated task output. Override in providers that support it."""
        return TaskSummaryResult()

    def distill_triage_lesson(self, payload: dict) -> dict:
        """Distil a reusable Triage Lesson from a cluster of resolved incidents (ADR-0030).

        `payload` describes the shared subject/source_kind and the cluster's resolved
        incidents (titles, closures, resolution comments). Returns
        ``{"guidance": str, "selector": str}`` — or ``{}`` to propose nothing (the default,
        so a provider without an implementation never fabricates lessons). For a Global
        proposal the guidance MUST be generalised and carry no tenant specifics (ADR-0031).
        """
        return {}

    def group_residual_alerts(self, alerts: list) -> ResidualGroupingResult:
        """Group residual (unlinked, settled) alerts into suspicious clusters. Override in providers that support it."""
        return ResidualGroupingResult()

    def generate_closure_message(self, incident_context: dict) -> str:
        """Generate a plain-language closure notification for a non-technical reporter. Returns empty string by default."""
        return ""

    def generate_report_summary(self, grounding: dict) -> str:
        """Generate an incident Report's executive summary from an audience-filtered
        grounding (PRD #621). MUST be grounded only on what it is passed — callers
        feed it ``build_report_grounding`` output, never ``build_incident_grounding``.
        Returns empty string by default."""
        return ""

    def generate_search_incident_summary(self, evidence: dict) -> str:
        """Generate a readable analyst summary of a scheduled-search incident's matched
        evidence (#644). Grounded ONLY on the evidence passed — the matched documents'
        raw source data — never inventing findings beyond it. Returns empty string by
        default so providers that do not implement it degrade gracefully."""
        return ""

    def assist_incident(self, messages: list, grounding: dict) -> AssistantResult:
        """Conversational assistant grounded in an incident's current state. Override in providers that support it."""
        return AssistantResult(assistant_reply="Assistant is not available for this provider.")

    def supports_complex_tools(self) -> bool:
        """True for Cloud-tier capable models that can drive the hunt general-query grammar (ADR-0026)."""
        return False
