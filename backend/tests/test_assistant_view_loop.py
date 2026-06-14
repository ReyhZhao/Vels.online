"""End-to-end: the assistant streaming view actually runs the agentic loop (ADR-0011/0014).

Uses a real provider with a mocked SDK client that emits a tool call, proving the
view -> orchestrator -> tool executor path is wired (not silently swallowed). This
guards against the loop no-op'ing in production.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from security.models import Organization
from incidents.models import Incident
from incidents.llm.base import AssistantResult
from incidents.llm.ollama import OllamaTriageProvider


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(organization=acme, title="Phish", display_id="INC-9", state="new", pap="green")


def _parse_sse_tool_events(content: str) -> list[dict]:
    """Extract 'tool' type SSE events from streamed content."""
    events = []
    event_type = None
    data_lines = []
    for line in content.splitlines():
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: "):])
        elif line == "" and event_type is not None:
            if event_type == "tool":
                events.append(json.loads("".join(data_lines)))
            event_type = None
            data_lines = []
    return events


async def _collect_stream(response) -> str:
    sc = response.streaming_content
    if hasattr(sc, "__aiter__"):
        return b"".join([chunk async for chunk in sc]).decode()
    return b"".join(sc).decode()


@pytest.mark.django_db(transaction=True)
async def test_incident_assistant_runs_web_search_tool(async_client, staff, incident, settings):
    settings.OLLAMA_API_KEY = "cloudkey"          # web_search_available() -> True
    settings.OLLAMA_BASE_URL = "https://ollama.com"

    provider = OllamaTriageProvider()
    turn_call = SimpleNamespace(message=SimpleNamespace(
        content="",
        tool_calls=[SimpleNamespace(
            function=SimpleNamespace(name="web_search", arguments={"query": "CVE-2025-1"}), id="c1")],
    ))
    turn_done = SimpleNamespace(message=SimpleNamespace(content="searched", tool_calls=[]))
    provider._client = MagicMock()
    provider._client.chat.side_effect = [turn_call, turn_done]
    provider.assist_incident = MagicMock(
        return_value=AssistantResult(assistant_reply="done", proposed_actions=[], warnings=[]))

    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider), \
         patch("assistants.web_search._ollama_web_search",
               return_value=[{"title": "t", "url": "u", "content": "c"}]) as ws:
        res = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "search the web for CVE-2025-1"}]},
            content_type="application/json",
        )

    assert res.status_code == 200, res.content
    content = await _collect_stream(res)
    tool_events = _parse_sse_tool_events(content)
    assert ws.called, "web_search backend was never invoked by the loop"
    assert any(t["tool"] == "web_search" for t in tool_events), f"no web_search tool event in: {content}"


@pytest.mark.django_db(transaction=True)
async def test_incident_assistant_records_findings_on_manual_task(async_client, staff, incident, settings):
    """Asking the assistant to work tasks must actually call add_task_comment and
    create a real task-scoped comment — not merely narrate it (#515)."""
    from asgiref.sync import sync_to_async
    from incidents.models import Task, Comment

    task = await sync_to_async(Task.objects.create)(
        incident=incident, title="Check sender domain", task_type=Task.TYPE_MANUAL, state="new",
    )

    provider = OllamaTriageProvider()
    turn_call = SimpleNamespace(message=SimpleNamespace(
        content="",
        tool_calls=[SimpleNamespace(
            function=SimpleNamespace(
                name="add_task_comment",
                arguments={"task_id": task.id, "text": "Domain registered 2 days ago; suspicious."}),
            id="c1")],
    ))
    turn_done = SimpleNamespace(message=SimpleNamespace(content="recorded findings", tool_calls=[]))
    provider._client = MagicMock()
    provider._client.chat.side_effect = [turn_call, turn_done]
    provider.assist_incident = MagicMock(
        return_value=AssistantResult(
            assistant_reply="Recorded findings on the manual task.", proposed_actions=[], warnings=[]))

    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        res = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "research the open tasks and update them"}]},
            content_type="application/json",
        )

    assert res.status_code == 200, res.content
    content = await _collect_stream(res)
    tool_events = _parse_sse_tool_events(content)
    assert any(t["tool"] == "add_task_comment" and t["error"] is None for t in tool_events), \
        f"add_task_comment not executed by the loop in: {content}"

    comment = await sync_to_async(
        lambda: Comment.objects.filter(task=task, is_internal=True).first())()
    assert comment is not None, "no task-scoped findings comment was persisted"
    assert "Domain registered 2 days ago" in comment.body
