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


async def _collect_sse_result(response) -> dict:
    """Consume a StreamingHttpResponse (SSE) and return the 'result' event data dict."""
    sc = response.streaming_content
    if hasattr(sc, "__aiter__"):
        content = b"".join([chunk async for chunk in sc]).decode()
    else:
        content = b"".join(sc).decode()
    event_type = None
    data_lines = []
    for line in content.splitlines():
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: "):])
        elif line == "" and event_type is not None:
            if event_type == "result":
                return json.loads("".join(data_lines))
            event_type = None
            data_lines = []
    return {}


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
    subject, _ = Subject.objects.get_or_create(slug="phishing", defaults={"name": "Phishing"})
    return subject


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
    mock = MagicMock(spec=["assist_incident"])
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

@pytest.mark.django_db(transaction=True)
async def test_assistant_response_shape(async_client, staff, incident):
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider("Severity is medium.")):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
    assert "assistant_reply" in data
    assert "proposed_actions" in data
    assert "warnings" in data
    assert data["assistant_reply"] == "Severity is medium."
    assert isinstance(data["proposed_actions"], list)


# ── proposed action: update_field ─────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_assistant_proposes_update_field(async_client, staff, incident):
    action = ProposedAction(
        type="update_field",
        label="Upgrade severity to High",
        payload={"field": "severity", "value": "high"},
    )
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
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
def test_ollama_assist_incident_constrains_json_and_recovers_envelope_from_prose(incident):
    """The Ollama synthesis call must force JSON output, and even when the model wraps the
    envelope in reasoning prose the reply + proposed_actions must be parsed (issue #455)."""
    from incidents.llm.ollama import OllamaTriageProvider

    grounding = build_incident_grounding(incident)
    # Reasoning preamble followed by the real envelope — the exact failure mode in the issue.
    raw_response = (
        "Add comment internal summarizing findings.\n\n"
        "We'll output JSON with those actions and reply.\n\n"
        + json.dumps({
            "assistant_reply": "Severity should be raised to high.",
            "proposed_actions": [
                {"type": "update_field", "field": "severity", "value": "high", "label": "Raise severity"},
            ],
        })
    )

    mock_provider = MagicMock(spec=OllamaTriageProvider)
    mock_response = MagicMock()
    mock_response.message.content = raw_response
    mock_provider._client = MagicMock()
    mock_provider._client.chat.return_value = mock_response
    mock_provider._model = "mistral"

    result = OllamaTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    # The synthesis call is constrained to JSON output (parity with Gemini).
    assert mock_provider._client.chat.call_args.kwargs.get("format") == "json"
    # The embedded envelope was recovered: clean reply, no reasoning preamble or raw blob.
    assert result.assistant_reply == "Severity should be raised to high."
    assert "We'll output JSON" not in result.assistant_reply
    assert "{" not in result.assistant_reply
    # The proposed action survived rather than being dropped.
    severity_actions = [a for a in result.proposed_actions if a.payload.get("field") == "severity"]
    assert len(severity_actions) == 1
    assert severity_actions[0].payload["value"] == "high"


@pytest.mark.django_db
def test_ollama_assist_incident_failed_json_does_not_dump_raw_blob(incident):
    """A genuinely unparseable JSON-looking reply must degrade to a safe generic reply,
    never surfacing the model's reasoning or a literal JSON blob (issue #455)."""
    from incidents.llm.ollama import OllamaTriageProvider

    grounding = build_incident_grounding(incident)
    # Looks like a JSON attempt but is malformed and unrecoverable.
    raw_response = 'Reasoning: I will now answer. { "assistant_reply": "oops broken'

    mock_provider = MagicMock(spec=OllamaTriageProvider)
    mock_response = MagicMock()
    mock_response.message.content = raw_response
    mock_provider._client = MagicMock()
    mock_provider._client.chat.return_value = mock_response
    mock_provider._model = "mistral"

    result = OllamaTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert "{" not in result.assistant_reply
    assert "Reasoning:" not in result.assistant_reply
    assert result.proposed_actions == []
    assert len(result.warnings) == 1


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

@pytest.mark.django_db(transaction=True)
async def test_assistant_proposes_transition_state(async_client, staff, incident):
    action = ProposedAction(
        type="transition_state",
        label="Move to In Progress",
        payload={"state": "in_progress"},
    )
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
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


# ── proposed action: closing an incident (#458) ───────────────────────────────
# These exercise the shared envelope parser, so both the Gemini and Ollama paths
# (which both delegate to _parse_assistant_result) inherit the behaviour.

@pytest.mark.django_db
def test_assistant_close_proposal_carries_closure_reason(incident):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    assert "closed" in grounding["allowed_transitions"]
    data = {
        "assistant_reply": "Closing as a false positive.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed",
             "closure_reason": "false_positive", "label": "Close as false positive"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert len(result.proposed_actions) == 1
    act = result.proposed_actions[0]
    assert act.type == "transition_state"
    assert act.payload == {"state": "closed", "closure_reason": "false_positive"}


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["resolved", "informational", "accepted_risk"])
def test_assistant_close_proposal_accepts_every_non_duplicate_reason(incident, reason):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Closing.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed",
             "closure_reason": reason, "label": "Close"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].payload == {"state": "closed", "closure_reason": reason}


@pytest.mark.django_db
def test_assistant_close_without_closure_reason_dropped(incident):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Closing.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed", "label": "Close"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert result.proposed_actions == []
    assert any("closure_reason" in w for w in result.warnings)


@pytest.mark.django_db
def test_assistant_close_with_invalid_closure_reason_dropped(incident):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Closing.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed",
             "closure_reason": "because_i_said_so", "label": "Close"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert result.proposed_actions == []
    assert any("closure_reason" in w for w in result.warnings)


@pytest.mark.django_db
def test_assistant_close_as_duplicate_carries_canonical_reference(incident, acme, phishing):
    from incidents.llm.gemini import _parse_assistant_result

    canonical = Incident.objects.create(
        organization=acme, title="Canonical", display_id="INC-2026-0001",
        severity="medium", state="new", subject=phishing,
    )
    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Duplicate of the canonical incident.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed",
             "closure_reason": "duplicate", "duplicate_of": canonical.id,
             "label": "Close as duplicate"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].payload == {
        "state": "closed", "closure_reason": "duplicate", "duplicate_of": canonical.id,
    }


@pytest.mark.django_db
def test_assistant_close_as_duplicate_without_reference_dropped(incident):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Duplicate.",
        "proposed_actions": [
            {"type": "transition_state", "state": "closed",
             "closure_reason": "duplicate", "label": "Close as duplicate"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert result.proposed_actions == []
    assert any("duplicate_of" in w for w in result.warnings)


@pytest.mark.django_db
def test_assistant_non_close_transition_carries_only_state(incident):
    from incidents.llm.gemini import _parse_assistant_result

    grounding = build_incident_grounding(incident)
    data = {
        "assistant_reply": "Moving to in progress.",
        "proposed_actions": [
            {"type": "transition_state", "state": "in_progress", "label": "Start work"},
        ],
    }
    result = _parse_assistant_result(data, grounding)
    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].payload == {"state": "in_progress"}


@pytest.mark.django_db
def test_grounding_includes_closure_reasons(incident):
    g = build_incident_grounding(incident)
    assert g["closure_reasons"] == [v for v, _ in Incident.CLOSURE_REASON_CHOICES]


# ── proposed action: apply_task_template ──────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_assistant_proposes_apply_task_template(async_client, staff, incident, template):
    action = ProposedAction(
        type="apply_task_template",
        label="Apply Phishing Playbook",
        payload={"template_id": template.id, "template_name": template.name},
    )
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
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


@pytest.mark.django_db
def test_grounding_tasks_expose_id_description_and_type(incident):
    t = Task.objects.create(
        incident=incident, title="Check sender domain",
        description="Look up the sending domain reputation",
        task_type=Task.TYPE_MANUAL, display_order=1,
    )
    g = build_incident_grounding(incident)
    row = next(r for r in g["tasks"] if r["title"] == "Check sender domain")
    assert row["id"] == t.id
    assert row["description"] == "Look up the sending domain reputation"
    assert row["task_type"] == Task.TYPE_MANUAL


@pytest.mark.django_db
def test_grounding_includes_applied_template_names(incident, template, staff):
    from incidents.services.templates import apply_template
    apply_template(incident, template, actor=staff)
    g = build_incident_grounding(incident)
    assert g["applied_templates"] == ["Phishing Playbook"]


@pytest.mark.django_db
def test_grounding_applied_templates_empty_when_none(incident):
    g = build_incident_grounding(incident)
    assert g["applied_templates"] == []


# ── grounding: contacts ────────────────────────────────────────────────────────

@pytest.fixture
def contact(db, acme):
    from contacts.models import Contact
    return Contact.objects.create(organisation=acme, name="Alice Smith", email="alice@example.com")


@pytest.fixture
def incident_contact(db, incident, contact):
    from contacts.models import IncidentContact
    return IncidentContact.objects.create(incident=incident, contact=contact)


@pytest.mark.django_db
def test_grounding_includes_contacts(incident, incident_contact, contact):
    g = build_incident_grounding(incident)
    assert "contacts" in g
    assert any(c["id"] == contact.id and c["name"] == contact.name for c in g["contacts"])


@pytest.mark.django_db
def test_grounding_contacts_empty_when_none(incident):
    g = build_incident_grounding(incident)
    assert g["contacts"] == []


# ── proposed action: create_comment ───────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_assistant_create_comment_action_proposed(async_client, staff, incident):
    action = ProposedAction(
        type="create_comment",
        label="Add internal note",
        payload={"text": "Check the firewall logs.", "internal": True},
    )
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
    assert len(data["proposed_actions"]) == 1
    act = data["proposed_actions"][0]
    assert act["type"] == "create_comment"
    assert act["payload"]["text"] == "Check the firewall logs."
    assert act["payload"]["internal"] is True


@pytest.mark.django_db
def test_gemini_create_comment_defaults_to_internal(incident):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    raw_response = json.dumps({
        "assistant_reply": "Adding a note.",
        "proposed_actions": [
            {"type": "create_comment", "text": "Suspicious login detected.", "label": "Add note"},
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

    assert len(result.proposed_actions) == 1
    assert result.proposed_actions[0].payload["internal"] is True


@pytest.mark.django_db
def test_gemini_create_comment_empty_text_stripped(incident):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    raw_response = json.dumps({
        "assistant_reply": ".",
        "proposed_actions": [
            {"type": "create_comment", "text": "", "label": "Empty"},
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


# ── proposed action: send_contact_message ─────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_assistant_send_contact_message_proposed(async_client, staff, incident, incident_contact, contact):
    action = ProposedAction(
        type="send_contact_message",
        label=f"Notify {contact.name}",
        payload={"contact_id": contact.id, "message": "Please investigate.", "contact_name": contact.name},
    )
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=[action])):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
    assert len(data["proposed_actions"]) == 1
    act = data["proposed_actions"][0]
    assert act["type"] == "send_contact_message"
    assert act["payload"]["contact_id"] == contact.id
    assert act["payload"]["message"] == "Please investigate."


@pytest.mark.django_db
def test_gemini_send_contact_message_valid_contact(incident, incident_contact, contact):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    raw_response = json.dumps({
        "assistant_reply": "Notifying contact.",
        "proposed_actions": [
            {
                "type": "send_contact_message",
                "contact_id": contact.id,
                "message": "Your system may be compromised.",
                "label": f"Notify {contact.name}",
            },
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

    assert len(result.proposed_actions) == 1
    pa = result.proposed_actions[0]
    assert pa.type == "send_contact_message"
    assert pa.payload["contact_id"] == contact.id
    assert pa.payload["contact_name"] == contact.name
    assert result.warnings == []


@pytest.mark.django_db
def test_gemini_send_contact_message_unknown_contact_stripped(incident):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    # No contacts attached to this incident
    raw_response = json.dumps({
        "assistant_reply": "Notifying contact.",
        "proposed_actions": [
            {
                "type": "send_contact_message",
                "contact_id": 999999,
                "message": "You are hacked.",
                "label": "Notify unknown",
            },
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


@pytest.mark.django_db
def test_gemini_send_contact_message_empty_message_stripped(incident, incident_contact, contact):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    raw_response = json.dumps({
        "assistant_reply": ".",
        "proposed_actions": [
            {"type": "send_contact_message", "contact_id": contact.id, "message": "", "label": "Empty"},
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


# ── prose fallback: non-JSON response treated as assistant_reply ───────────────

@pytest.mark.django_db
def test_gemini_prose_fallback_returns_result(incident):
    """When Gemini returns non-JSON prose, assist_incident must return an AssistantResult
    with the prose as assistant_reply and an empty proposed_actions list."""
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    grounding = build_incident_grounding(incident)
    prose = "Om een commentaar toe te voegen, moet je naar de incidentpagina gaan."

    mock_provider = MagicMock(spec=GeminiTriageProvider)
    mock_response = MagicMock()
    mock_response.text = prose
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_provider._client = mock_client
    mock_provider._types = genai_types

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.assistant_reply == prose
    assert result.proposed_actions == []
    assert len(result.warnings) == 1
    assert "plain text" in result.warnings[0]


@pytest.mark.django_db
def test_ollama_prose_fallback_returns_result(incident):
    """When Ollama returns non-JSON prose, assist_incident must return an AssistantResult
    with the prose as assistant_reply and an empty proposed_actions list."""
    from incidents.llm.ollama import OllamaTriageProvider

    grounding = build_incident_grounding(incident)
    prose = "This CVE affects OpenSSL versions prior to 3.0.7 and has a CVSS score of 7.5."

    mock_provider = MagicMock(spec=OllamaTriageProvider)
    mock_response = MagicMock()
    mock_response.message.content = prose
    mock_provider._client = MagicMock()
    mock_provider._client.chat.return_value = mock_response
    mock_provider._model = "mistral"

    result = OllamaTriageProvider.assist_incident(mock_provider, _MESSAGES, grounding)

    assert result.assistant_reply == prose
    assert result.proposed_actions == []
    assert len(result.warnings) == 1
    assert "plain text" in result.warnings[0]


@pytest.mark.django_db(transaction=True)
async def test_gemini_prose_fallback_returns_200_via_endpoint(async_client, staff, incident):
    """Endpoint must return 200 when the provider falls back to prose (no 502)."""
    from incidents.llm.base import AssistantResult
    prose_result = AssistantResult(
        assistant_reply="Dit is een informatieve tekst over het incident.",
        proposed_actions=[],
        warnings=["Provider returned plain text instead of the expected JSON envelope; proposed actions are unavailable."],
    )
    mock = MagicMock()
    mock.assist_incident.return_value = prose_result

    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=mock):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")

    assert resp.status_code == 200
    data = await _collect_sse_result(resp)
    assert data["assistant_reply"] == prose_result.assistant_reply
    assert data["proposed_actions"] == []
    assert len(data["warnings"]) == 1


# ── existing action types continue to work ────────────────────────────────────

@pytest.mark.django_db(transaction=True)
async def test_existing_action_types_unaffected(async_client, staff, incident):
    actions = [
        ProposedAction(type="update_field", label="Set severity", payload={"field": "severity", "value": "high"}),
        ProposedAction(type="transition_state", label="Move to in_progress", payload={"state": "in_progress"}),
    ]
    await async_client.aforce_login(staff)
    with patch("incidents.llm.factory.get_assistant_provider", return_value=_mock_provider(actions=actions)):
        resp = await async_client.post(_URL(incident), data=json.dumps({"messages": _MESSAGES}), content_type="application/json")
    data = await _collect_sse_result(resp)
    types = [a["type"] for a in data["proposed_actions"]]
    assert "update_field" in types
    assert "transition_state" in types


# ── research-phase prompt drives task-working via add_task_comment (#515) ──────
# Regression: the instruction to work manual tasks (call add_task_comment) must live
# in the tool-executing research prompt, not only the tool-less synthesis prompt —
# otherwise the assistant narrates having recorded findings while no tool ever runs.

def test_research_prompt_lists_manual_tasks_with_ids_and_tool_instruction(db, incident):
    from incidents.views import _build_research_sys_prompt
    manual = Task.objects.create(
        incident=incident, title="Check sender domain reputation",
        description="Look up the sender domain age and reputation",
        task_type=Task.TYPE_MANUAL, state="new",
    )
    prompt = _build_research_sys_prompt(build_incident_grounding(incident))
    assert "add_task_comment" in prompt
    assert f"task_id={manual.id}" in prompt
    assert "Check sender domain reputation" in prompt


def test_research_prompt_steers_per_task_work_away_from_incident_comment(db, incident):
    """Regression (#680): per-task findings must go on the task via add_task_comment,
    never as an incident-wide add_internal_comment, and the model must not claim a task
    is completed/closed/done."""
    from incidents.views import _build_research_sys_prompt
    Task.objects.create(incident=incident, title="Draft incident summary",
                        task_type=Task.TYPE_MANUAL, state="new")
    prompt = _build_research_sys_prompt(build_incident_grounding(incident)).lower()
    assert "add_internal_comment" in prompt      # names the wrong tool to steer away from it
    assert "completed" in prompt                 # forbids claiming completion


def test_research_prompt_excludes_non_manual_tasks_from_workable_list(db, incident):
    from incidents.views import _build_research_sys_prompt
    manual = Task.objects.create(incident=incident, title="Manual step",
                                 task_type=Task.TYPE_MANUAL, state="new")
    automated = Task.objects.create(incident=incident, title="Run playbook",
                                    task_type=Task.TYPE_AUTOMATED, state="new")
    wazuh = Task.objects.create(incident=incident, title="Isolate host",
                                task_type=Task.TYPE_WAZUH_RESPONSE, state="new")
    prompt = _build_research_sys_prompt(build_incident_grounding(incident))
    assert f"task_id={manual.id}" in prompt
    assert f"task_id={automated.id}" not in prompt
    assert f"task_id={wazuh.id}" not in prompt


def test_research_prompt_without_manual_tasks_omits_task_instruction(db, incident):
    from incidents.views import _build_research_sys_prompt
    Task.objects.create(incident=incident, title="Run playbook",
                        task_type=Task.TYPE_AUTOMATED, state="new")
    prompt = _build_research_sys_prompt(build_incident_grounding(incident))
    assert "add_task_comment" not in prompt
    assert "Stop once you have what you need." in prompt


def test_synthesis_prompt_does_not_instruct_calling_task_tool(db, incident):
    """Synthesis is tool-less; it must report on findings, not instruct a tool call."""
    from incidents.llm.gemini import _build_assistant_system_prompt
    Task.objects.create(incident=incident, title="Manual step",
                        task_type=Task.TYPE_MANUAL, state="new")
    prompt = _build_assistant_system_prompt(build_incident_grounding(incident))
    # It must not tell the model to call the tool here (no tools in synthesis),
    # and must anchor reporting to research_notes.
    assert "call add_task_comment" not in prompt
    assert "research_notes" in prompt
