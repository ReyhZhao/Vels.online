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

    @abstractmethod
    def select_relevant_rule_ids(
        self,
        messages: list,
        grounding: dict,
    ) -> List[str]:
        """Pass 1: given messages and grounding (with rule_catalog), return relevant rule.id list."""

    @abstractmethod
    def draft_search_rule(
        self,
        messages: list,
        grounding: dict,
        current_draft: Optional[dict] = None,
    ) -> RuleDraftResult:
        """Pass 2: given messages and expanded grounding, return a drafted search rule."""

    def generate_sample_docs(self, grounding: dict, expect_fire: bool) -> list:
        """Generate synthetic Sample Documents for a Rule Test (PRD #439).

        Returns a list of partial raw Wazuh document dicts. Default implementation is
        unsupported; concrete providers override it. Not abstract so existing providers
        keep working without change.
        """
        raise DraftError("This provider does not support sample-document generation.")
