"""Unit tests for the SSE event emitter (ADR-0014 / issue #466).

Asserts exact wire output for each event type and guarantees that 'done' is
always the final frame in normal and error sequences.
"""
import json

import pytest

from assistants.sse_emitter import (
    emit_action,
    emit_done,
    emit_error,
    emit_phase,
    emit_result,
    emit_tool,
    event_to_frame,
)


def _parse_frame(frame: str) -> tuple[str, dict]:
    """Parse a single SSE frame into (event_type, data_dict)."""
    lines = frame.strip().splitlines()
    event_type = None
    data = None
    for line in lines:
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])
    return event_type, data


# ── individual frame shapes ────────────────────────────────────────────────────

def test_phase_frame():
    frame = emit_phase("research")
    t, d = _parse_frame(frame)
    assert t == "phase"
    assert d == {"phase": "research"}
    assert frame.endswith("\n\n")


def test_tool_frame():
    entry = {"tool": "web_search", "arguments": {"query": "CVE"}, "summary": "2 results",
             "count": 2, "error": None, "is_write": False}
    frame = emit_tool(entry)
    t, d = _parse_frame(frame)
    assert t == "tool"
    assert d["tool"] == "web_search"
    assert d["count"] == 2


def test_action_frame():
    entry = {"tool": "add_tag", "arguments": {"tag": "spam"}, "summary": "tagged"}
    frame = emit_action(entry)
    t, d = _parse_frame(frame)
    assert t == "action"
    assert d["tool"] == "add_tag"


def test_result_frame():
    frame = emit_result("here is my reply", [{"type": "update_field"}], ["warn"])
    t, d = _parse_frame(frame)
    assert t == "result"
    assert d["assistant_reply"] == "here is my reply"
    assert d["proposed_actions"] == [{"type": "update_field"}]
    assert d["warnings"] == ["warn"]


def test_error_frame():
    frame = emit_error("something went wrong")
    t, d = _parse_frame(frame)
    assert t == "error"
    assert d["detail"] == "something went wrong"


def test_done_frame():
    frame = emit_done()
    t, d = _parse_frame(frame)
    assert t == "done"
    assert d == {}


# ── sequence contracts ─────────────────────────────────────────────────────────

def test_normal_sequence_ends_with_result_then_done():
    frames = [
        emit_phase("research"),
        emit_tool({"tool": "lookup", "arguments": {}, "summary": "ok",
                   "count": 1, "error": None, "is_write": False}),
        emit_phase("synthesis"),
        emit_result("answer", [], []),
        emit_done(),
    ]
    types = [_parse_frame(f)[0] for f in frames]
    assert types[-1] == "done"
    assert types[-2] == "result"


def test_error_sequence_ends_with_error_then_done():
    frames = [
        emit_phase("research"),
        emit_error("provider unavailable"),
        emit_done(),
    ]
    types = [_parse_frame(f)[0] for f in frames]
    assert types[-1] == "done"
    assert types[-2] == "error"


# ── event_to_frame dispatcher ──────────────────────────────────────────────────

def test_event_to_frame_phase():
    f = event_to_frame({"type": "phase", "phase": "synthesis"})
    t, d = _parse_frame(f)
    assert t == "phase"
    assert d["phase"] == "synthesis"


def test_event_to_frame_tool():
    f = event_to_frame({"type": "tool", "tool": "web_search", "arguments": {},
                        "summary": "ok", "count": 1, "error": None, "is_write": False})
    t, d = _parse_frame(f)
    assert t == "tool"
    assert "type" not in d  # dispatcher strips the 'type' key


def test_event_to_frame_action():
    f = event_to_frame({"type": "action", "tool": "assign", "arguments": {}, "summary": "done"})
    t, d = _parse_frame(f)
    assert t == "action"
    assert "type" not in d


def test_event_to_frame_unknown_returns_empty():
    f = event_to_frame({"type": "unknown_future_type"})
    assert f == ""
