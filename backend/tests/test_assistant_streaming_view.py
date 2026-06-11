"""Integration tests for the Incident Assistant streaming endpoint (ADR-0014 / issue #467).

Drives the streaming endpoint end-to-end with a fake provider and asserts:
- Event ordering: phase -> tool(s) -> action(s) -> phase -> result -> done
- Pre-stream HTTP error paths: 403 (not-staff), 404 (not-visible), 503 (provider unavailable)
- Post-open terminal error path: error + done
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from incidents.llm.base import AssistantConfigError, AssistantResult
from incidents.models import Incident
from security.models import Organization


def _parse_sse(content: str) -> list[dict]:
    """Parse SSE text into a list of {"event": str, "data": dict} dicts."""
    events = []
    event_type = None
    data_lines = []
    for line in content.splitlines():
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: "):])
        elif line == "" and event_type is not None:
            data = json.loads("".join(data_lines)) if data_lines else {}
            events.append({"event": event_type, "data": data})
            event_type = None
            data_lines = []
    return events


async def _collect_stream(response) -> str:
    """Collect all chunks from a StreamingHttpResponse (sync or async generator)."""
    sc = response.streaming_content
    if hasattr(sc, "__aiter__"):
        return b"".join([chunk async for chunk in sc]).decode()
    return b"".join(sc).decode()


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="p", is_staff=False)


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(
        organization=acme, title="Phish", display_id="INC-STREAM-1", state="new", pap="green"
    )


def _make_fake_provider():
    provider = MagicMock()
    provider.uses_native_web_search = MagicMock(return_value=False)
    provider.chat.return_value = MagicMock(text="done", tool_calls=[])
    provider.assist_incident.return_value = AssistantResult(
        assistant_reply="here is my analysis", proposed_actions=[], warnings=[]
    )
    return provider


# ── pre-stream HTTP error paths ───────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_pre_stream_401_not_authenticated(async_client, incident):
    response = await async_client.post(
        f"/api/incidents/{incident.display_id}/assistant/",
        {"messages": [{"role": "user", "content": "hi"}]},
        content_type="application/json",
    )
    # DRF's IsAuthenticated returns 401 before the view handler runs
    assert response.status_code == 401
    assert not response.streaming


@pytest.mark.django_db(transaction=True)
async def test_pre_stream_403_not_staff(async_client, regular_user, incident):
    await async_client.aforce_login(regular_user)
    response = await async_client.post(
        f"/api/incidents/{incident.display_id}/assistant/",
        {"messages": [{"role": "user", "content": "hi"}]},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not response.streaming


@pytest.mark.django_db(transaction=True)
async def test_pre_stream_404_incident_not_found(async_client, staff):
    await async_client.aforce_login(staff)
    response = await async_client.post(
        "/api/incidents/INC-NONEXISTENT/assistant/",
        {"messages": [{"role": "user", "content": "hi"}]},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert not response.streaming


@pytest.mark.django_db(transaction=True)
async def test_pre_stream_503_provider_unavailable(async_client, staff, incident):
    await async_client.aforce_login(staff)
    with patch(
        "incidents.llm.factory.get_assistant_provider",
        side_effect=AssistantConfigError("no provider"),
    ):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "hi"}]},
            content_type="application/json",
        )
    assert response.status_code == 503
    assert not response.streaming


@pytest.mark.django_db(transaction=True)
async def test_pre_stream_400_messages_missing(async_client, staff, incident):
    await async_client.aforce_login(staff)
    provider = _make_fake_provider()
    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": []},
            content_type="application/json",
        )
    assert response.status_code == 400
    assert not response.streaming


# ── normal streaming sequence ─────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_event_ordering_normal_turn(async_client, staff, incident):
    await async_client.aforce_login(staff)
    provider = _make_fake_provider()

    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "analyse this"}]},
            content_type="application/json",
        )

    assert response.status_code == 200
    content = await _collect_stream(response)
    events = _parse_sse(content)

    types = [e["event"] for e in events]
    assert types[-1] == "done"
    assert "result" in types
    # result comes before done
    assert types.index("result") < types.index("done")
    # synthesis phase marker present
    assert any(e["event"] == "phase" and e["data"].get("phase") == "synthesis" for e in events)


@pytest.mark.django_db(transaction=True)
async def test_streaming_response_headers(async_client, staff, incident):
    await async_client.aforce_login(staff)
    provider = _make_fake_provider()

    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "hi"}]},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.get("Content-Type", "")
    assert response.get("X-Accel-Buffering") == "no"


# ── post-open terminal error path ─────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_post_open_error_emits_error_then_done(async_client, staff, incident):
    """Once the stream is open, a provider error is emitted as error + done."""
    await async_client.aforce_login(staff)
    provider = _make_fake_provider()
    provider.assist_incident.side_effect = Exception("provider blew up")
    provider.chat.return_value = MagicMock(text="done", tool_calls=[])

    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "hi"}]},
            content_type="application/json",
        )

    assert response.status_code == 200  # stream already opened
    content = await _collect_stream(response)
    events = _parse_sse(content)
    types = [e["event"] for e in events]

    assert "error" in types
    assert types[-1] == "done"
    assert types.index("error") < types.index("done")
    error_event = next(e for e in events if e["event"] == "error")
    assert "detail" in error_event["data"]


# ── result content ─────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_result_event_carries_assistant_reply(async_client, staff, incident):
    await async_client.aforce_login(staff)
    provider = _make_fake_provider()
    provider.assist_incident.return_value = AssistantResult(
        assistant_reply="your incident is serious", proposed_actions=[], warnings=[]
    )

    with patch("incidents.llm.factory.get_assistant_provider", return_value=provider):
        response = await async_client.post(
            f"/api/incidents/{incident.display_id}/assistant/",
            {"messages": [{"role": "user", "content": "assess"}]},
            content_type="application/json",
        )

    content = await _collect_stream(response)
    events = _parse_sse(content)
    result_event = next(e for e in events if e["event"] == "result")
    assert result_event["data"]["assistant_reply"] == "your incident is serious"
