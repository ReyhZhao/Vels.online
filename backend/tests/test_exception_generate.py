import json
import pytest
from unittest.mock import MagicMock, patch

from security.models import Organization, OrganizationMembership
from incidents.models import Incident
from exceptions.llm.base import BaseLLMProvider, ExceptionFields


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_wazuh_incident(acme, display_id="INC-2026-0001"):
    return Incident.objects.create(
        display_id=display_id,
        organization=acme,
        title="Brute force detected",
        source_kind="wazuh_event",
        source_ref={"rule": {"id": "5763", "description": "Login failed"}, "agent": {"name": "web-01"}},
    )


def make_stub_provider(fields: ExceptionFields):
    provider = MagicMock(spec=BaseLLMProvider)
    provider.generate_exception.return_value = fields
    return provider


FULL_FIELDS = ExceptionFields(
    trigger_rule_id=5763,
    description="Suppress login failure from web-01",
    match_value=None,
    field_name="agent.name",
    field_value="web-01",
    field_type="literal",
    agent_name="web-01",
)

MINIMAL_FIELDS = ExceptionFields(
    trigger_rule_id=5763,
    description="Suppress alert",
)


# ── BaseLLMProvider / ExceptionFields ────────────────────────────────────────


def test_exception_fields_defaults():
    f = ExceptionFields(trigger_rule_id=100, description="test")
    assert f.match_value is None
    assert f.field_name is None
    assert f.field_value is None
    assert f.field_type is None
    assert f.agent_name is None


def test_base_provider_is_abstract():
    with pytest.raises(TypeError):
        BaseLLMProvider()


def test_stub_provider_satisfies_interface():
    stub = make_stub_provider(FULL_FIELDS)
    result = stub.generate_exception({"rule": {"id": "5763"}})
    assert result.trigger_rule_id == 5763


# ── POST /api/exceptions/generate/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_generate_requires_auth(client, acme):
    make_wazuh_incident(acme)
    response = client.post(
        "/api/exceptions/generate/",
        {"display_id": "INC-2026-0001"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_generate_rejects_non_staff(client, acme_member, acme):
    make_wazuh_incident(acme)
    client.force_login(acme_member)
    response = client.post(
        "/api/exceptions/generate/",
        {"display_id": "INC-2026-0001"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_generate_returns_400_without_display_id(admin_client):
    response = admin_client.post(
        "/api/exceptions/generate/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_generate_returns_404_for_unknown_incident(admin_client):
    response = admin_client.post(
        "/api/exceptions/generate/",
        {"display_id": "INC-DOES-NOT-EXIST"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_generate_rejects_non_wazuh_incident(admin_client, acme):
    Incident.objects.create(
        display_id="INC-2026-0002",
        organization=acme,
        title="Manual",
        source_kind="manual",
    )
    response = admin_client.post(
        "/api/exceptions/generate/",
        {"display_id": "INC-2026-0002"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "wazuh_event" in response.json()["detail"]


@pytest.mark.django_db
def test_generate_returns_full_fields(admin_client, acme):
    make_wazuh_incident(acme)
    with patch("exceptions.views.get_llm_provider", return_value=make_stub_provider(FULL_FIELDS)):
        response = admin_client.post(
            "/api/exceptions/generate/",
            {"display_id": "INC-2026-0001"},
            content_type="application/json",
        )
    assert response.status_code == 200
    data = response.json()
    assert data["trigger_rule_id"] == 5763
    assert data["description"] == "Suppress login failure from web-01"
    assert data["field_name"] == "agent.name"
    assert data["field_value"] == "web-01"
    assert data["field_type"] == "literal"
    assert data["agent_name"] == "web-01"
    assert data["match_value"] is None


@pytest.mark.django_db
def test_generate_optional_fields_default_to_none(admin_client, acme):
    make_wazuh_incident(acme)
    with patch("exceptions.views.get_llm_provider", return_value=make_stub_provider(MINIMAL_FIELDS)):
        response = admin_client.post(
            "/api/exceptions/generate/",
            {"display_id": "INC-2026-0001"},
            content_type="application/json",
        )
    assert response.status_code == 200
    data = response.json()
    assert data["trigger_rule_id"] == 5763
    assert data["description"] == "Suppress alert"
    assert data["match_value"] is None
    assert data["field_name"] is None
    assert data["field_value"] is None
    assert data["field_type"] is None
    assert data["agent_name"] is None


@pytest.mark.django_db
def test_generate_passes_source_ref_to_provider(admin_client, acme):
    incident = make_wazuh_incident(acme)
    stub = make_stub_provider(MINIMAL_FIELDS)
    with patch("exceptions.views.get_llm_provider", return_value=stub):
        admin_client.post(
            "/api/exceptions/generate/",
            {"display_id": "INC-2026-0001"},
            content_type="application/json",
        )
    stub.generate_exception.assert_called_once_with(incident.source_ref)


@pytest.mark.django_db
def test_generate_returns_502_on_provider_error(admin_client, acme):
    make_wazuh_incident(acme)
    stub = MagicMock()
    stub.generate_exception.side_effect = RuntimeError("LLM unavailable")
    with patch("exceptions.views.get_llm_provider", return_value=stub):
        response = admin_client.post(
            "/api/exceptions/generate/",
            {"display_id": "INC-2026-0001"},
            content_type="application/json",
        )
    assert response.status_code == 502
    assert "LLM provider error" in response.json()["detail"]


@pytest.mark.django_db
def test_generate_returns_400_for_empty_source_ref(admin_client, acme):
    Incident.objects.create(
        display_id="INC-2026-0099",
        organization=acme,
        title="Empty ref",
        source_kind="wazuh_event",
        source_ref={},
    )
    response = admin_client.post(
        "/api/exceptions/generate/",
        {"display_id": "INC-2026-0099"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "no Wazuh alert data" in response.json()["detail"]


# ── OllamaProvider ───────────────────────────────────────────────────────────


SOURCE_REF = {"rule": {"id": "5763", "description": "Login failed"}, "agent": {"name": "web-01"}}

OLLAMA_RESPONSE_PAYLOAD = {
    "trigger_rule_id": 5763,
    "description": "Suppress login failure from web-01",
    "field_name": "agent.name",
    "field_value": "web-01",
    "field_type": "literal",
    "agent_name": "web-01",
}


def _make_ollama_chat_response(payload: dict):
    msg = MagicMock()
    msg.content = json.dumps(payload)
    resp = MagicMock()
    resp.message = msg
    return resp


def _make_ollama_client(chat_return):
    client = MagicMock()
    client.chat.return_value = chat_return
    return client


@patch("exceptions.llm.ollama.ollama")
def test_ollama_provider_returns_exception_fields(mock_ollama_mod, settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.OLLAMA_MODEL = "mistral"
    mock_client = _make_ollama_client(_make_ollama_chat_response(OLLAMA_RESPONSE_PAYLOAD))
    mock_ollama_mod.Client.return_value = mock_client

    from exceptions.llm.ollama import OllamaProvider
    provider = OllamaProvider()
    result = provider.generate_exception(SOURCE_REF)

    assert result.trigger_rule_id == 5763
    assert result.description == "Suppress login failure from web-01"
    assert result.field_name == "agent.name"
    assert result.field_value == "web-01"
    assert result.field_type == "literal"
    assert result.agent_name == "web-01"
    assert result.match_value is None


@patch("exceptions.llm.ollama.ollama")
def test_ollama_provider_strips_markdown_fences(mock_ollama_mod, settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.OLLAMA_MODEL = "mistral"
    fenced = f"```json\n{json.dumps(OLLAMA_RESPONSE_PAYLOAD)}\n```"
    msg = MagicMock()
    msg.content = fenced
    resp = MagicMock()
    resp.message = msg
    mock_client = _make_ollama_client(resp)
    mock_ollama_mod.Client.return_value = mock_client

    from exceptions.llm.ollama import OllamaProvider
    provider = OllamaProvider()
    result = provider.generate_exception(SOURCE_REF)

    assert result.trigger_rule_id == 5763


@patch("exceptions.llm.ollama.ollama")
def test_ollama_provider_passes_source_ref_as_json(mock_ollama_mod, settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.OLLAMA_MODEL = "mistral"
    mock_client = _make_ollama_client(_make_ollama_chat_response(OLLAMA_RESPONSE_PAYLOAD))
    mock_ollama_mod.Client.return_value = mock_client

    from exceptions.llm.ollama import OllamaProvider
    provider = OllamaProvider()
    provider.generate_exception(SOURCE_REF)

    call_kwargs = mock_client.chat.call_args
    messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][1]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert json.loads(user_msg["content"]) == SOURCE_REF


@patch("exceptions.llm.ollama.ollama")
def test_ollama_provider_raises_on_invalid_json(mock_ollama_mod, settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    settings.OLLAMA_MODEL = "mistral"
    msg = MagicMock()
    msg.content = "not valid json"
    resp = MagicMock()
    resp.message = msg
    mock_ollama_mod.Client.return_value = _make_ollama_client(resp)

    from exceptions.llm.ollama import OllamaProvider
    provider = OllamaProvider()
    with pytest.raises(Exception):
        provider.generate_exception(SOURCE_REF)
