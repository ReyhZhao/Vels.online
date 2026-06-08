"""The agentic loop orchestrator (ADR-0011).

Phase 1 (research) lives here: the orchestrator repeatedly asks the provider for a
turn, executes any tool calls server-side, feeds the results back, and stops when
the model stops calling tools or a cap is hit. Phase 2 (synthesis) is the caller's
job — it reuses the existing structured-output path (draft_rule / proposed_actions)
with the research transcript appended via `research_notes()`.

The orchestrator is provider-agnostic: drive it in tests with a fake provider that
emits scripted `ChatTurn`s. It never imports an LLM SDK.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from django.conf import settings

from .tools import ChatTurn, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


@dataclass
class LoopCaps:
    max_iterations: int = 5
    per_tool_timeout_s: float = 10.0
    # Total research-loop budget. Must stay below the gunicorn --timeout (backend/Dockerfile)
    # so the loop self-limits before gunicorn SIGABRT-kills the worker.
    deadline_s: float = 60.0
    max_auto_actions: int = 8

    @classmethod
    def from_settings(cls) -> "LoopCaps":
        return cls(
            max_iterations=int(getattr(settings, "ASSISTANT_LOOP_MAX_ITERATIONS", 5)),
            per_tool_timeout_s=float(getattr(settings, "ASSISTANT_TOOL_TIMEOUT_S", 10.0)),
            deadline_s=float(getattr(settings, "ASSISTANT_LOOP_DEADLINE_S", 60.0)),
            max_auto_actions=int(getattr(settings, "ASSISTANT_MAX_AUTO_ACTIONS", 8)),
        )


@dataclass
class ResearchResult:
    messages: List[dict]                       # full transcript incl tool results
    tool_trace: List[dict] = field(default_factory=list)
    auto_actions: List[dict] = field(default_factory=list)
    stop_reason: str = "model_done"            # model_done | max_iterations | deadline


def _summarize_args(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > 120:
            out[k] = v[:117] + "..."
        else:
            out[k] = v
    return out


def _content_str(result: ToolResult) -> str:
    if result.error:
        return json.dumps({"error": result.error})
    try:
        return json.dumps(result.content, default=str)
    except (TypeError, ValueError):
        return str(result.content)


def _run_with_timeout(executor, arguments: dict, timeout_s: float) -> ToolResult:
    """Run a tool executor with a best-effort per-tool timeout."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(executor, arguments)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout:
            return ToolResult(error="tool timed out", summary="timed out")
        except Exception as exc:  # a tool blowing up must not kill the turn
            logger.warning("tool executor raised: %s", exc)
            return ToolResult(error=f"tool error: {exc}", summary="error")


def _is_duplicate(name: str, arguments: dict, auto_actions: List[dict]) -> bool:
    return any(
        a["tool"] == name and a["arguments"] == arguments for a in auto_actions
    )


def run_research_phase(
    provider,
    tools: List[ToolSpec],
    messages: List[dict],
    caps: Optional[LoopCaps] = None,
    clock: Callable[[], float] = time.monotonic,
) -> ResearchResult:
    """Run the phase-1 research loop and return the enriched transcript + trace.

    `provider` must expose `chat(messages, tools) -> ChatTurn`.
    """
    caps = caps or LoopCaps.from_settings()
    registry = {t.name: t for t in tools}
    transcript: List[dict] = list(messages)
    trace: List[dict] = []
    auto_actions: List[dict] = []
    start = clock()
    iterations = 0
    stop_reason = "model_done"

    while True:
        if iterations >= caps.max_iterations:
            stop_reason = "max_iterations"
            break
        if clock() - start >= caps.deadline_s:
            stop_reason = "deadline"
            break
        iterations += 1

        turn: ChatTurn = provider.chat(transcript, tools)

        if not turn.tool_calls:
            if turn.text:
                transcript.append({"role": "assistant", "content": turn.text})
            stop_reason = "model_done"
            break

        # Echo the assistant turn carrying the tool calls BEFORE the tool results, so
        # the next iteration sees a well-formed call/result history (required by Ollama).
        transcript.append({
            "role": "assistant",
            "content": turn.text or "",
            "tool_calls": [
                {"name": c.name, "arguments": c.arguments, "id": c.id} for c in turn.tool_calls
            ],
        })

        for call in turn.tool_calls:
            spec = registry.get(call.name)
            is_write = bool(spec and spec.is_write)

            if spec is None:
                result = ToolResult(error=f"unknown tool '{call.name}'", summary="unknown tool")
            elif is_write and len(auto_actions) >= caps.max_auto_actions:
                result = ToolResult(error="auto-action cap reached for this turn", summary="capped")
            elif is_write and _is_duplicate(call.name, call.arguments, auto_actions):
                result = ToolResult(error="duplicate action skipped", summary="duplicate skipped")
            else:
                result = _run_with_timeout(spec.executor, call.arguments, caps.per_tool_timeout_s)

            trace.append({
                "tool": call.name,
                "arguments": _summarize_args(call.arguments),
                "summary": result.summary,
                "count": result.count,
                "error": result.error,
                "is_write": is_write,
            })

            if is_write and result.error is None:
                auto_actions.append({
                    "tool": call.name,
                    "arguments": call.arguments,
                    "summary": result.summary,
                })

            transcript.append({
                "role": "tool",
                "name": call.name,
                "tool_call_id": call.id,
                "content": _content_str(result),
            })

    return ResearchResult(
        messages=transcript,
        tool_trace=trace,
        auto_actions=auto_actions,
        stop_reason=stop_reason,
    )


def research_notes(result: ResearchResult) -> str:
    """Render the research transcript into a compact notes block for phase-2 synthesis."""
    if not result.tool_trace:
        return ""
    lines = ["The following was gathered while researching this request:"]
    for entry, msg in _pair_trace_with_results(result):
        args = entry.get("arguments") or {}
        head = f"- {entry['tool']}({json.dumps(args, default=str)})"
        if entry.get("error"):
            lines.append(f"{head} -> error: {entry['error']}")
        else:
            lines.append(f"{head} -> {msg}")
    return "\n".join(lines)


def _pair_trace_with_results(result: ResearchResult):
    """Yield (trace_entry, tool_result_content) pairs in order."""
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    for i, entry in enumerate(result.tool_trace):
        content = tool_msgs[i]["content"] if i < len(tool_msgs) else ""
        if isinstance(content, str) and len(content) > 800:
            content = content[:797] + "..."
        yield entry, content
