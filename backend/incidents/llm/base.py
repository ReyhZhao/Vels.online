from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


VALID_ACTIONS = {
    "escalate",
    "create_exception",
    "assign_to_analyst",
    "close_as_false_positive",
    "monitor",
    "close_as_informational",
}

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


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


class BaseTriageProvider(ABC):
    @abstractmethod
    def triage_incident(self, payload: dict) -> TriageResult:
        """Analyse an incident payload and return a triage assessment."""
