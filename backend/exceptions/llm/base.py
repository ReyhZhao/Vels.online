from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExceptionFields:
    trigger_rule_id: Optional[int] = None
    description: str = ""
    match_value: Optional[str] = None
    field_name: Optional[str] = None
    field_value: Optional[str] = None
    field_type: Optional[str] = None
    agent_name: Optional[str] = None


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_exception(self, source_ref: dict) -> ExceptionFields:
        """Analyse a Wazuh event's source_ref and propose exception rule fields."""
