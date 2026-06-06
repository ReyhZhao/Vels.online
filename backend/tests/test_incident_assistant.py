import json
from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent, Subject, Task, TaskTemplate, TaskTemplateItem
from incidents.llm.base import AssistantResult, ProposedAction, ASSISTANT_FIELD_ALLOWLIST
from incidents.llm.grounding import build_incident_grounding
from incidents.services.transitions import ALLOWED_TRANSITIONS


# ── fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="pass", is_staff=False)


@pytest.fixture
def member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


@pytest.fixture
def incident(db, acme, phishing):
    return Incident.objects.create(
        organization=acme,
        title="Suspected phishing",
        display_id="INC-2026-0099",
        severity="medium",
        state="new",
        subject=phishing,
    )


@pytest.fixture
def template(db, phishing, staff):
    t = TaskTemplate.objects.create(name="Phishing Playbook", subject=phishing, created_by=staff)
    TaskTemplateItem.objects.create(template=t, title="Step 1", description="Block sender", display_order=1)
    return t


_MESSAGES = [{"role": "user", "content": "What is the current severity?"}]
_URL = lambda inc: f"/api/incidents/{inc.display_id}/assistant/"


def _mock_provider(reply="Here is the severity.", actions=None):
    result = AssistantResult(
        assistant_reply=reply,
        proposed_actions=actions or [],
        warnings=[],
    )
    mock = MagicMock()
    mock.assist_incident.return_value = result
    return mock


# ── access control ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_requires_auth(client, incident):
    resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_assistant_requires_staff(client, member, incident):
    client.force_login(member)
    resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_assistant_staff_can_access(client, staff, incident):
    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider()):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    assert resp.status_code == 200


# ── request validation ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_missing_messages_returns_400(client, staff, incident):
    client.force_login(staff)
    resp = client.post(_URL(incident), data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_assistant_unknown_incident_returns_404(client, staff, acme):
    client.force_login(staff)
    resp = client.post(
        "/api/incidents/INC-NOTREAL/assistant/",
        data=json.dumps({"messages": _MESSAGES}),
        content_type="application/json",
    )
    assert resp.status_code == 404


# ── statelessness: grounding is recomputed server-side ─────────────────────────

@pytest.mark.django_db
def test_assistant_grounding_not_trusted_from_client(client, staff, incident):
    """Client cannot inject grounding — the endpoint ignores any grounding in the request body."""
    client.force_login(staff)
    captured = {}

    def capture_and_reply(messages, grounding):
        captured["grounding"] = grounding
        return AssistantResult(assistant_reply="ok", proposed_actions=[], warnings=[])

    mock = MagicMock()
    mock.assist_incident.side_effect = capture_and_reply

    payload = {
        "messages": _MESSAGES,
        "grounding": {"incident": {"severity": "critical", "state": "closed"}},
    }
    with patch("incidents.llm.factory.get_assistant_provider", return_value=mock):
        resp = client.post(_URL(incident), data=json.dumps(payload), content_type="application/json")

    assert resp.status_code == 200
    # Grounding was recomputed; attacker-injected 'closed' state is ignored.
    assert captured["grounding"]["incident"]["state"] == "new"
    assert captured["grounding"]["incident"]["severity"] == "medium"


# ── response shape ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_response_shape(client, staff, incident):
    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider("Severity is medium.")):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = resp.json()
    assert "assistant_reply" in data
    assert "proposed_actions" in data
    assert "warnings" in data
    assert data["assistant_reply"] == "Severity is medium."
    assert isinstance(data["proposed_actions"], list)


# ── proposed action: update_field ─────────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_proposes_update_field(client, staff, incident):
    action = ProposedAction(
        type="update_field",
        label="Upgrade severity to High",
        payload={"field": "severity", "value": "high"},
    )
    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = resp.json()
    assert len(data["proposed_actions"]) == 1
    act = data["proposed_actions"][0]
    assert act["type"] == "update_field"
    assert act["payload"]["field"] == "severity"
    assert act["payload"]["value"] == "high"


@pytest.mark.django_db
def test_assistant_field_allowlist_enforced_in_gemini_provider(incident):
    """GeminiTriageProvider.assist_incident must strip update_field actions for non-allowlisted fields."""
    from incidents.llm.gemini import GeminiTriageProvider

    grounding = build_incident_grounding(incident)

    raw_response = json.dumps({
        "assistant_reply": "Here is my suggestion.",
        "proposed_actions": [
            {"type": "update_field", "field": "display_id", "value": "HACKED", "label": "Bad action"},
            {"type": "update_field", "field": "severity", "value": "high", "label": "Good action"},
        ],
    })

    mock_provider = MagicMock(spec=GeminiTriageProvider)
    mock_provider.assist_incident = GeminiTriageProvider.assist_incident.__get__(mock_provider, GeminiTriageProvider)

    from google.genai import types as genai_types
    mock_response = MagicMock()
    mock_response.text = raw_response
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_provider._client = mock_client
    mock_provider._types = genai_types

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    # display_id is not in the allowlist — must be stripped
    assert all(a.payload.get("field") != "display_id" for a in result.proposed_actions)
    # severity is allowlisted — must survive
    severity_actions = [a for a in result.proposed_actions if a.payload.get("field") == "severity"]
    assert len(severity_actions) == 1
    assert len(result.warnings) >= 1


@pytest.mark.django_db
def test_ollama_assist_incident_parses_and_enforces_allowlist(incident):
    """OllamaTriageProvider.assist_incident must parse replies/actions and strip non-allowlisted fields."""
    from incidents.llm.ollama import OllamaTriageProvider

    grounding = build_incident_grounding(incident)

    raw_response = json.dumps({
        "assistant_reply": "Here is my suggestion.",
        "proposed_actions": [
            {"type": "update_field", "field": "display_id", "value": "HACKED", "label": "Bad action"},
            {"type": "update_field", "field": "severity", "value": "high", "label": "Good action"},
        ],
    })

    mock_provider = MagicMock(spec=OllamaTriageProvider)
    mock_response = MagicMock()
    mock_response.message.content = raw_response
    mock_provider._client = MagicMock()
    mock_provider._client.chat.return_value = mock_response
    mock_provider._model = "mistral"

    result = OllamaTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.assistant_reply == "Here is my suggestion."
    # display_id is not allowlisted — must be stripped
    assert all(a.payload.get("field") != "display_id" for a in result.proposed_actions)
    severity_actions = [a for a in result.proposed_actions if a.payload.get("field") == "severity"]
    assert len(severity_actions) == 1
    assert len(result.warnings) >= 1


@pytest.mark.django_db
def test_ollama_assist_incident_strips_code_fence(incident):
    """OllamaTriageProvider.assist_incident must handle JSON wrapped in a markdown code fence."""
    from incidents.llm.ollama import OllamaTriageProvider

    grounding = build_incident_grounding(incident)
    raw_response = "```json\n" + json.dumps({"assistant_reply": "Fenced reply.", "proposed_actions": []}) + "\n```"

    mock_provider = MagicMock(spec=OllamaTriageProvider)
    mock_response = MagicMock()
    mock_response.message.content = raw_response
    mock_provider._client = MagicMock()
    mock_provider._client.chat.return_value = mock_response
    mock_provider._model = "mistral"

    result = OllamaTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.assistant_reply == "Fenced reply."
    assert result.proposed_actions == []


# ── proposed action: transition_state ─────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_proposes_transition_state(client, staff, incident):
    action = ProposedAction(
        type="transition_state",
        label="Move to In Progress",
        payload={"state": "in_progress"},
    )
    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = resp.json()
    assert data["proposed_actions"][0]["type"] == "transition_state"
    assert data["proposed_actions"][0]["payload"]["state"] == "in_progress"


@pytest.mark.django_db
def test_assistant_illegal_transition_stripped(incident):
    """GeminiTriageProvider.assist_incident must strip a transition to a state not allowed from the current state."""
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    # incident state is "new"; "resolved" is not in ALLOWED_TRANSITIONS["new"]
    assert "resolved" not in ALLOWED_TRANSITIONS.get("new", set())

    raw_response = json.dumps({
        "assistant_reply": "Propose illegal transition.",
        "proposed_actions": [
            {"type": "transition_state", "state": "resolved", "label": "Bad"},
        ],
    })

    mock_provider = MagicMock(spec=GeminiTriageProvider)
    mock_response = MagicMock()
    mock_response.text = raw_response
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_provider._client = mock_client
    mock_provider._types = genai_types

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.proposed_actions == []
    assert len(result.warnings) >= 1


# ── proposed action: apply_task_template ──────────────────────────────────────

@pytest.mark.django_db
def test_assistant_proposes_apply_task_template(client, staff, incident, template):
    action = ProposedAction(
        type="apply_task_template",
        label="Apply Phishing Playbook",
        payload={"template_id": template.id, "template_name": template.name},
    )
    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = resp.json()
    act = data["proposed_actions"][0]
    assert act["type"] == "apply_task_template"
    assert act["payload"]["template_id"] == template.id


@pytest.mark.django_db
def test_assistant_wrong_subject_template_stripped(incident, template):
    """GeminiTriageProvider.assist_incident strips templates that don't belong to the incident's subject."""
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    # Use a fake template_id that is NOT in available_templates
    fake_id = 999999

    raw_response = json.dumps({
        "assistant_reply": "Apply this template.",
        "proposed_actions": [
            {"type": "apply_task_template", "template_id": fake_id, "label": "Bad template"},
        ],
    })

    mock_provider = MagicMock(spec=GeminiTriageProvider)
    mock_response = MagicMock()
    mock_response.text = raw_response
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_provider._client = mock_client
    mock_provider._types = genai_types

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.proposed_actions == []
    assert len(result.warnings) >= 1


# ── provider unavailable ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_assistant_unconfigured_provider_returns_503(client, staff, incident):
    from incidents.llm.base import TriageConfigError

    client.force_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", side_effect=TriageConfigError("No API key.")):
        resp = client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")

    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


# ── grounding builder ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_grounding_includes_incident_fields(incident):
    g = build_incident_grounding(incident)
    inc = g["incident"]
    assert inc["display_id"] == incident.display_id
    assert inc["title"] == incident.title
    assert inc["severity"] == incident.severity
    assert inc["state"] == incident.state
    assert inc["subject"] == incident.subject.name


@pytest.mark.django_db
def test_grounding_includes_allowed_transitions(incident):
    g = build_incident_grounding(incident)
    expected = sorted(ALLOWED_TRANSITIONS.get("new", set()))
    assert g["allowed_transitions"] == expected


@pytest.mark.django_db
def test_grounding_includes_available_templates(incident, template):
    g = build_incident_grounding(incident)
    template_ids = [t["id"] for t in g["available_templates"]]
    assert template.id in template_ids


@pytest.mark.django_db
def test_grounding_no_templates_when_no_subject(acme):
    inc = Incident.objects.create(
        organization=acme, title="No subject", display_id="INC-2026-NO-SUBJ",
    )
    g = build_incident_grounding(inc)
    assert g["available_templates"] == []


@pytest.mark.django_db
def test_grounding_field_allowlist_present(incident):
    g = build_incident_grounding(incident)
    assert set(g["field_allowlist"]) == ASSISTANT_FIELD_ALLOWLIST


@pytest.mark.django_db
def test_grounding_includes_tasks(incident):
    Task.objects.create(incident=incident, title="Investigate email", display_order=1)
    g = build_incident_grounding(incident)
    assert any(t["title"] == "Investigate email" for t in g["tasks"])
