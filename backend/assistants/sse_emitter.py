"""SSE wire-frame emitter for the Incident Assistant streaming endpoint (ADR-0014).

Maps orchestrator events into correctly framed SSE records. This module owns the
event protocol so it can be tested in isolation — no view, no async, no network.

Event types emitted:
  phase  — {"phase": "research" | "synthesis"}
  tool   — tool call/result (same shape as tool_trace entries)
  action — auto-executed write that committed (same shape as auto_actions entries)
  result — terminal structured envelope: assistant_reply, proposed_actions, warnings
  error  — {"detail": str}
  done   — {} — always the final frame, including on the error path
"""
import json


def _frame(event_type: str, data: dict) -> str:
    """Produce a single SSE record: event + data lines followed by a blank line."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def emit_phase(phase: str) -> str:
    return _frame("phase", {"phase": phase})


def emit_tool(entry: dict) -> str:
    return _frame("tool", entry)


def emit_action(entry: dict) -> str:
    return _frame("action", entry)


def emit_result(assistant_reply: str, proposed_actions: list, warnings: list) -> str:
    return _frame("result", {
        "assistant_reply": assistant_reply,
        "proposed_actions": proposed_actions,
        "warnings": warnings,
    })


def emit_error(detail: str) -> str:
    return _frame("error", {"detail": detail})


def emit_done() -> str:
    return _frame("done", {})


def event_to_frame(event: dict) -> str:
    """Convert an orchestrator event dict (as emitted by on_event) to an SSE frame."""
    t = event.get("type")
    if t == "phase":
        return emit_phase(event["phase"])
    if t == "tool":
        return emit_tool({k: v for k, v in event.items() if k != "type"})
    if t == "action":
        return emit_action({k: v for k, v in event.items() if k != "type"})
    return ""
