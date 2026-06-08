"""Tests for the Gemini tool-calling adapter (ADR-0011, #453).

Stub the Gemini SDK shapes and assert the adapter (a) combines native google_search
grounding with custom function declarations in one request and (b) normalises
function_call / text parts into the orchestrator's ChatTurn.
"""
from types import SimpleNamespace

from assistants.providers import _parse_gemini_response, gemini_chat
from assistants.tools import ToolSpec


def _spec(name="lookup_incidents"):
    return ToolSpec(name=name, description="d", parameters={"type": "object", "properties": {}},
                    executor=lambda a: None)


# ── response parsing ─────────────────────────────────────────────────────────

def test_parse_function_call_part():
    fc = SimpleNamespace(name="lookup_incidents", args={"query": "phish"})
    part = SimpleNamespace(function_call=fc, text=None)
    resp = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    turn = _parse_gemini_response(resp)
    assert turn.tool_calls[0].name == "lookup_incidents"
    assert turn.tool_calls[0].arguments == {"query": "phish"}
    assert turn.text == ""


def test_parse_text_part():
    part = SimpleNamespace(function_call=None, text="here is the answer")
    resp = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    turn = _parse_gemini_response(resp)
    assert turn.text == "here is the answer"
    assert turn.tool_calls == []


# ── full chat turn translation ───────────────────────────────────────────────

class _FakeTypes:
    Content = staticmethod(lambda role, parts: SimpleNamespace(role=role, parts=parts))
    GoogleSearch = staticmethod(lambda: SimpleNamespace(kind="google_search"))
    Tool = staticmethod(lambda google_search=None, function_declarations=None:
                        SimpleNamespace(google_search=google_search, function_declarations=function_declarations))
    FunctionDeclaration = staticmethod(lambda name, description, parameters: SimpleNamespace(name=name))
    GenerateContentConfig = staticmethod(lambda system_instruction=None, tools=None:
                                         SimpleNamespace(system_instruction=system_instruction, tools=tools))

    class Part:
        from_text = staticmethod(lambda text: SimpleNamespace(text=text))
        from_function_response = staticmethod(lambda name, response: SimpleNamespace(name=name, response=response))


class _FakeModels:
    def __init__(self, resp):
        self.resp = resp
        self.last = None

    def generate_content(self, model, contents, config):
        self.last = {"model": model, "contents": contents, "config": config}
        return self.resp


class _FakeClient:
    def __init__(self, resp):
        self.models = _FakeModels(resp)


def test_gemini_chat_combines_grounding_and_function_tools():
    fc = SimpleNamespace(name="lookup_incidents", args={"query": "x"})
    resp = SimpleNamespace(candidates=[
        SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(function_call=fc, text=None)]))
    ])
    client = _FakeClient(resp)
    turn = gemini_chat(client, _FakeTypes, "gemini-3-flash", "system prompt",
                       [{"role": "user", "content": "any related?"}], [_spec()], with_grounding=True)

    cfg_tools = client.models.last["config"].tools
    # one Tool carries google_search grounding, another carries our function decls
    assert any(getattr(t, "google_search", None) is not None for t in cfg_tools)
    assert any(getattr(t, "function_declarations", None) for t in cfg_tools)
    assert turn.tool_calls[0].name == "lookup_incidents"


def test_gemini_chat_grounding_can_be_disabled():
    resp = SimpleNamespace(candidates=[
        SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(function_call=None, text="hi")]))
    ])
    client = _FakeClient(resp)
    gemini_chat(client, _FakeTypes, "gemini-3-flash", "", [{"role": "user", "content": "hi"}],
                [_spec()], with_grounding=False)
    cfg_tools = client.models.last["config"].tools
    assert all(getattr(t, "google_search", None) is None for t in cfg_tools)
