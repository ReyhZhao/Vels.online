"""End-to-end: the assistant views actually run the agentic loop (ADR-0011).

Uses a real provider with a mocked SDK client that emits a tool call, proving the
view -> orchestrator -> tool executor path is wired (not silently swallowed). This
guards against the loop no-op'ing in production.
"""
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


def test_incident_assistant_runs_web_search_tool(client, staff, incident, settings):
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

    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider), \
         patch("assistants.web_search._ollama_web_search",
               return_value=[{"title": "t", "url": "u", "content": "c"}]) as ws:
        res = client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "search the web for CVE-2025-1"}]},
            content_type="application/json",
        )

    assert res.status_code == 200, res.content
    body = res.json()
    assert ws.called, "web_search backend was never invoked by the loop"
    assert any(t["tool"] == "web_search" for t in body.get("tool_trace", [])), body
