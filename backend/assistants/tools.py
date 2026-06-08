"""Provider-agnostic tool and chat types for the agentic loop (ADR-0011).

A `ToolSpec` is a single tool the model may call: a name, a JSON-schema parameter
shape, an `executor` the orchestrator runs server-side, and an `is_write` flag
marking it as an auto-executed action (ADR-0012) rather than a read-only lookup.

Providers translate the generic `ToolSpec` list + message transcript into their own
SDK shape and translate the response back into a `ChatTurn` (free text and/or
`ToolCall`s). The orchestrator never touches a provider SDK directly.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class ToolCall:
    """A single tool invocation the model asked for."""
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""


@dataclass
class ChatTurn:
    """One provider response: free text, tool calls, or both."""
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)


@dataclass
class ToolResult:
    """The outcome of executing a tool, fed back to the model and the tool_trace."""
    content: Any = None
    error: Optional[str] = None
    summary: str = ""          # short human description for the tool_trace
    count: Optional[int] = None  # number of items returned, when meaningful


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                                # JSON schema (an "object")
    executor: Callable[[dict], ToolResult]          # run server-side by the orchestrator
    is_write: bool = False                          # auto-executed action (ADR-0012)

    def to_function_schema(self) -> dict:
        """OpenAI/Ollama-style function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
