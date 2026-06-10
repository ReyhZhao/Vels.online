"""Tests for the shared agentic loop (ADR-0011): orchestrator, web_search tool, PAP guard.

These assert external behaviour through the public interface, driving the loop with a
fake provider that emits scripted ChatTurns — never touching an LLM SDK.
"""
import pytest

from assistants.orchestrator import LoopCaps, run_research_phase, research_notes
from assistants.tools import ChatTurn, ToolCall, ToolResult, ToolSpec
from assistants.web_search import build_web_search_tool
from assistants import pap_guard


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeProvider:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if self._turns:
            return self._turns.pop(0)
        return ChatTurn(text="done")


def _echo_tool(name="lookup", is_write=False, record=None):
    def executor(args):
        if record is not None:
            record.append(args)
        return ToolResult(content={"echo": args}, summary=f"{name} ok", count=1)
    return ToolSpec(name=name, description="d", parameters={"type": "object", "properties": {}},
                    executor=executor, is_write=is_write)


CAPS = LoopCaps(max_iterations=5, per_tool_timeout_s=5, deadline_s=100, max_auto_actions=3)


# ── orchestrator: termination ───────────────────────────────────────────────────

def test_loop_stops_when_model_emits_no_tool_calls():
    provider = FakeProvider([ChatTurn(text="here is my answer")])
    result = run_research_phase(provider, [_echo_tool()], [{"role": "user", "content": "hi"}], CAPS)
    assert result.stop_reason == "model_done"
    assert len(provider.calls) == 1
    assert result.tool_trace == []


def test_loop_executes_tool_and_feeds_result_back():
    calls = []
    tool = _echo_tool(name="lookup_incidents", record=calls)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="lookup_incidents", arguments={"query": "phish"}, id="c1")]),
        ChatTurn(text="found related incidents"),
    ])
    result = run_research_phase(provider, [tool], [{"role": "user", "content": "any related?"}], CAPS)
    assert result.stop_reason == "model_done"
    assert calls == [{"query": "phish"}]              # tool actually ran
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0]["tool"] == "lookup_incidents"
    assert result.tool_trace[0]["error"] is None
    # the tool result was fed back into the transcript for the next turn
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "echo" in tool_msgs[0]["content"]


def test_max_iterations_cap_enforced():
    # provider always wants another tool call
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="lookup", arguments={})]) for _ in range(20)
    ])
    caps = LoopCaps(max_iterations=3, per_tool_timeout_s=5, deadline_s=100, max_auto_actions=8)
    result = run_research_phase(provider, [_echo_tool()], [{"role": "user", "content": "go"}], caps)
    assert result.stop_reason == "max_iterations"
    assert len(provider.calls) == 3


def test_deadline_cap_enforced_via_injected_clock():
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="lookup", arguments={})]) for _ in range(20)
    ])
    ticks = iter([0, 0, 999])  # third check is past the deadline
    result = run_research_phase(
        provider, [_echo_tool()], [{"role": "user", "content": "go"}],
        LoopCaps(max_iterations=50, per_tool_timeout_s=5, deadline_s=100, max_auto_actions=8),
        clock=lambda: next(ticks),
    )
    assert result.stop_reason == "deadline"


def test_loop_self_limits_when_chat_is_slow():
    """A slow provider.chat must not run the loop forever: the loop's own deadline stops it
    on the real wall clock (issue #454 — the budget must self-limit before gunicorn intervenes)."""
    import time

    class SlowProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools):
            self.calls += 1
            time.sleep(0.05)  # each turn overruns the tiny deadline below
            return ChatTurn(tool_calls=[ToolCall(name="lookup", arguments={})])

    provider = SlowProvider()
    caps = LoopCaps(max_iterations=50, per_tool_timeout_s=5, deadline_s=0.02, max_auto_actions=8)
    result = run_research_phase(provider, [_echo_tool()], [{"role": "user", "content": "go"}], caps)
    assert result.stop_reason == "deadline"
    # Stopped early on the deadline rather than running all 50 iterations.
    assert provider.calls < 50


def test_unknown_tool_is_reported_not_fatal():
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="does_not_exist", arguments={})]),
        ChatTurn(text="ok"),
    ])
    result = run_research_phase(provider, [_echo_tool(name="lookup")], [{"role": "user", "content": "go"}], CAPS)
    assert result.tool_trace[0]["error"] is not None
    assert "unknown" in result.tool_trace[0]["error"]
    assert result.stop_reason == "model_done"


# ── orchestrator: write/auto actions ─────────────────────────────────────────────

def test_write_tool_recorded_as_auto_action():
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="add_internal_comment", arguments={"text": "noted"})]),
        ChatTurn(text="done"),
    ])
    tool = _echo_tool(name="add_internal_comment", is_write=True)
    result = run_research_phase(provider, [tool], [{"role": "user", "content": "go"}], CAPS)
    assert len(result.auto_actions) == 1
    assert result.auto_actions[0]["tool"] == "add_internal_comment"
    assert result.tool_trace[0]["is_write"] is True


def test_duplicate_auto_action_skipped():
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="add_tag", arguments={"tag": "phish"})]),
        ChatTurn(tool_calls=[ToolCall(name="add_tag", arguments={"tag": "phish"})]),
        ChatTurn(text="done"),
    ])
    tool = _echo_tool(name="add_tag", is_write=True)
    result = run_research_phase(provider, [tool], [{"role": "user", "content": "go"}], CAPS)
    assert len(result.auto_actions) == 1                 # second is a duplicate
    assert result.tool_trace[1]["error"] is not None
    assert "duplicate" in result.tool_trace[1]["error"]


def test_auto_action_cap_enforced():
    turns = [ChatTurn(tool_calls=[ToolCall(name="add_tag", arguments={"tag": f"t{i}"})]) for i in range(5)]
    turns.append(ChatTurn(text="done"))
    provider = FakeProvider(turns)
    tool = _echo_tool(name="add_tag", is_write=True)
    caps = LoopCaps(max_iterations=10, per_tool_timeout_s=5, deadline_s=100, max_auto_actions=2)
    result = run_research_phase(provider, [tool], [{"role": "user", "content": "go"}], caps)
    assert len(result.auto_actions) == 2
    capped = [t for t in result.tool_trace if t["error"] and "cap" in t["error"]]
    assert capped


def test_tool_call_turn_echoed_before_result_in_transcript():
    # The assistant message carrying the tool_calls must precede the tool result,
    # so iteration 2 sees a well-formed call/result history (Ollama requirement).
    provider = FakeProvider([
        ChatTurn(text="let me check", tool_calls=[ToolCall(name="lookup", arguments={"q": 1}, id="c1")]),
        ChatTurn(text="done"),
    ])
    result = run_research_phase(provider, [_echo_tool(name="lookup")], [{"role": "user", "content": "go"}], CAPS)
    roles = [m.get("role") for m in result.messages]
    asst_with_calls = [m for m in result.messages if m.get("role") == "assistant" and m.get("tool_calls")]
    assert asst_with_calls, "assistant tool-call message was not appended"
    # the assistant tool-call message comes before the tool result
    asst_idx = next(i for i, m in enumerate(result.messages)
                    if m.get("role") == "assistant" and m.get("tool_calls"))
    tool_idx = next(i for i, m in enumerate(result.messages) if m.get("role") == "tool")
    assert asst_idx < tool_idx


def test_research_notes_render_tool_results():
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="web_search", arguments={"query": "CVE-2025-1"})]),
        ChatTurn(text="done"),
    ])
    tool = _echo_tool(name="web_search")
    result = run_research_phase(provider, [tool], [{"role": "user", "content": "go"}], CAPS)
    notes = research_notes(result)
    assert "web_search" in notes
    assert "CVE-2025-1" in notes


# ── web_search tool ─────────────────────────────────────────────────────────────

def test_web_search_tool_returns_results():
    tool = build_web_search_tool(search_fn=lambda q: [{"title": "t", "url": "u", "content": "c"}])
    res = tool.executor({"query": "ransomware"})
    assert res.error is None
    assert res.count == 1
    assert res.content[0]["url"] == "u"


def test_web_search_empty_query_errors():
    tool = build_web_search_tool(search_fn=lambda q: [])
    res = tool.executor({"query": "   "})
    assert res.error is not None


def test_web_search_guard_blocks_query():
    def guard(q):
        return (False, "blocked: PAP:RED")
    tool = build_web_search_tool(guard=guard, search_fn=lambda q: [{"x": 1}])
    res = tool.executor({"query": "1.2.3.4"})
    assert res.error == "blocked: PAP:RED"


# ── PAP egress guard ──────────────────────────────────────────────────────────

GROUNDING = {
    "incident": {"pap": "red", "assignee": "analyst1"},
    "iocs": [{"kind": "ip", "value": "203.0.113.5 (VirusTotal: 4/70 malicious)"},
             {"kind": "domain", "value": "evil.example.com"}],
    "assets": [{"name": "WEB-01", "agent_name": "agent-web-01", "ip_address": "10.0.0.5"}],
    "linked_alerts": [{"username": "jdoe"}],
}


def test_collect_indicators_pulls_iocs_assets_users():
    inds = pap_guard.collect_incident_indicators(GROUNDING)
    assert "203.0.113.5" in inds                 # IOC value, annotation stripped
    # Explicit element equality (not substring membership) so this stays a genuine
    # list-membership check — see CodeQL py/incomplete-url-substring-sanitization.
    assert any(ind == "evil.example.com" for ind in inds)
    assert "web-01" in inds
    assert "agent-web-01" in inds
    assert "10.0.0.5" in inds
    assert "jdoe" in inds
    assert "analyst1" not in inds                # the analyst is not an indicator


def test_pap_red_blocks_query_with_indicator():
    inds = pap_guard.collect_incident_indicators(GROUNDING)
    allowed, reason = pap_guard.check_web_search_query("reputation of 203.0.113.5", inds, "red")
    assert allowed is False
    assert "PAP:RED" in reason


def test_pap_red_blocks_domain_indicator():
    inds = pap_guard.collect_incident_indicators(GROUNDING)
    allowed, _ = pap_guard.check_web_search_query("is evil.example.com malicious?", inds, "red")
    assert allowed is False


def test_pap_red_allows_generic_query():
    inds = pap_guard.collect_incident_indicators(GROUNDING)
    allowed, reason = pap_guard.check_web_search_query("what is a golden ticket attack", inds, "red")
    assert allowed is True
    assert reason == ""


def test_non_red_pap_allows_indicator_query():
    inds = pap_guard.collect_incident_indicators(GROUNDING)
    for level in ("white", "green", "amber"):
        allowed, _ = pap_guard.check_web_search_query("reputation of 203.0.113.5", inds, level)
        assert allowed is True
