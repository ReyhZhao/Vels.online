from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


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
