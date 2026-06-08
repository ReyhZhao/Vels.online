"""Translation between the orchestrator's generic shapes and each provider SDK.

`ollama_chat` and `gemini_chat` are one turn of "chat with tools": they take the
generic transcript + ToolSpec list, call the SDK, and return a ChatTurn. They hold
NO agentic logic — the loop lives in the orchestrator (ADR-0011).
"""
import json
import logging

from .tools import ChatTurn, ToolCall, ToolSpec

logger = logging.getLogger(__name__)


# ── Ollama ──────────────────────────────────────────────────────────────────────

def _to_ollama_messages(messages: list) -> list:
    out = []
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            out.append({
                "role": "tool",
                "content": str(m.get("content", "")),
                "tool_name": m.get("name", ""),
            })
        else:
            out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def ollama_chat(client, model: str, messages: list, tools: list) -> ChatTurn:
    """One Ollama chat turn with tools. Returns a ChatTurn."""
    response = client.chat(
        model=model,
        messages=_to_ollama_messages(messages),
        tools=[t.to_function_schema() for t in tools] or None,
    )
    msg = response.message
    text = (getattr(msg, "content", "") or "").strip()
    calls = []
    for tc in (getattr(msg, "tool_calls", None) or []):
        fn = getattr(tc, "function", None) or {}
        name = getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else "")
        raw_args = getattr(fn, "arguments", None)
        if raw_args is None and isinstance(fn, dict):
            raw_args = fn.get("arguments")
        args = raw_args
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        calls.append(ToolCall(name=name or "", arguments=args or {}, id=getattr(tc, "id", "") or ""))
    return ChatTurn(text=text, tool_calls=calls)


# ── Gemini ────────────────────────────────────────────────────────────────────

def _to_gemini_contents(types, messages: list) -> list:
    contents = []
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            contents.append(types.Content(
                role="tool",
                parts=[types.Part.from_function_response(
                    name=m.get("name", ""),
                    response={"result": m.get("content", "")},
                )],
            ))
            continue
        if role == "assistant":
            role = "model"
        if role == "system":
            role = "user"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=str(m.get("content", "")))],
        ))
    return contents


def _gemini_tools_config(types, tools: list, with_grounding: bool):
    """Build the Gemini `tools` list: native Google Search grounding (Gemini 3)
    combined with our custom function declarations."""
    cfg_tools = []
    if with_grounding:
        cfg_tools.append(types.Tool(google_search=types.GoogleSearch()))
    decls = [
        types.FunctionDeclaration(
            name=t.name, description=t.description, parameters=t.parameters
        )
        for t in tools
    ]
    if decls:
        cfg_tools.append(types.Tool(function_declarations=decls))
    return cfg_tools


def gemini_chat(client, types, model: str, system_prompt: str, messages: list,
                tools: list, with_grounding: bool = True) -> ChatTurn:
    """One Gemini chat turn combining native grounding with custom function tools."""
    config = types.GenerateContentConfig(
        system_instruction=system_prompt or None,
        tools=_gemini_tools_config(types, tools, with_grounding) or None,
    )
    response = client.models.generate_content(
        model=model,
        contents=_to_gemini_contents(types, messages),
        config=config,
    )
    return _parse_gemini_response(response)


def _parse_gemini_response(response) -> ChatTurn:
    """Normalise a Gemini response (function_call parts + text) into a ChatTurn."""
    text_parts = []
    calls = []
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                args = getattr(fc, "args", None)
                if hasattr(args, "items"):
                    args = dict(args)
                calls.append(ToolCall(name=getattr(fc, "name", "") or "", arguments=args or {}))
                continue
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt)
    if not text_parts:
        # fall back to the SDK's convenience accessor when there are no parts
        try:
            t = (response.text or "").strip()
            if t:
                text_parts.append(t)
        except Exception:
            pass
    return ChatTurn(text="".join(text_parts).strip(), tool_calls=calls)
