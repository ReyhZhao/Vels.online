from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


class DraftError(Exception):
    """Raised when the LLM returns an unparseable or invalid draft response."""


class DraftConfigError(Exception):
    """Raised when the draft provider is misconfigured (missing API key, etc.).
    Not retriable — retrying will not fix a config problem."""


@dataclass
class RuleDraftResult:
    updated_draft: dict = field(default_factory=dict)
    assistant_reply: str = ""
    warnings: List[str] = field(default_factory=list)


class BaseDraftProvider(ABC):
    @abstractmethod
    def draft_rule(
        self,
        messages: list,
        grounding: dict,
        current_draft: Optional[dict] = None,
    ) -> RuleDraftResult:
        """Given conversation messages and vocabulary grounding, return a drafted or updated rule."""
