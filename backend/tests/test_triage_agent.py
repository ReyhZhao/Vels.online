"""Tests for the agentic Triage Work phase — the Triage Agent (ADR-0024).

Drive the loop with a scripted provider that emits ChatTurns — never an LLM SDK.
"""
from unittest.mock import MagicMock, patch

import pytest

from assistants.tools import ChatTurn, ToolCall
from incidents.llm.base import TriageResult
from incidents.models import Comment, Incident, Subject, Task, TaskTemplate, TaskTemplateItem
from incidents import triage_agent
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def phishing(db):
    subj, _ = Subject.objects.get_or_create(slug="phishing", defaults={"name": "Phishing"})
    return subj


def make_incident(acme, subject=None, state="triaged", **kw):
    n = Incident.objects.count()
    return Incident.objects.create(
        organization=acme, title="Suspicious login", description="x",
        display_id=f"INC-2026-{n + 1:04d}", state=state, subject=subject, **kw,
    )


def _result(disposition=0.9):
    return TriageResult(
        severity_recommendation="high", summary="s", primary_action="assign_to_analyst",
        disposition_confidence=disposition,
    )


class FakeProvider:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        return self._turns.pop(0) if self._turns else ChatTurn(text="done")


# ── the gate ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_gate_opens_on_high_confidence_with_subject(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    assert triage_agent.should_run_work_phase(inc, _result(0.95)) is True


@pytest.mark.django_db
def test_gate_closed_when_below_threshold(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    assert triage_agent.should_run_work_phase(inc, _result(0.5)) is False


@pytest.mark.django_db
def test_gate_closed_without_subject(acme):
    inc = make_incident(acme, subject=None)
    assert triage_agent.should_run_work_phase(inc, _result(0.99)) is False


@pytest.mark.django_db
def test_gate_respects_per_org_threshold(acme, phishing):
    acme.triage_work_threshold = 0.6
    acme.save()
    inc = make_incident(acme, subject=phishing)
    assert triage_agent.should_run_work_phase(inc, _result(0.7)) is True
    acme.triage_work_threshold = 0.99
    acme.save()
    inc.refresh_from_db()
    assert triage_agent.should_run_work_phase(inc, _result(0.7)) is False


@pytest.mark.django_db
def test_gate_closed_when_already_worked(acme, phishing):
    from django.utils import timezone
    inc = make_incident(acme, subject=phishing, triage_worked_at=timezone.now())
    assert triage_agent.should_run_work_phase(inc, _result(0.99)) is False


# ── the work phase ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_work_phase_research_then_handoff(acme, phishing):
    inc = make_incident(acme, subject=phishing, state="triaged")
    provider = FakeProvider([ChatTurn(text="Investigated; benign-looking but watch host web-01.")])

    triage_agent.run_triage_work(inc.id, provider=provider)

    inc.refresh_from_db()
    assert inc.state == Incident.STATE_IN_PROGRESS
    assert inc.triage_worked_at is not None
    comment = Comment.objects.get(incident=inc, kind=Comment.KIND_AI_TRIAGE)
    assert "web-01" in comment.body
    assert comment.author is None
    assert comment.metadata["triage_agent"] is True
    assert comment.metadata["phase"] == "work"
    assert comment.metadata["stop_reason"] == "model_done"


@pytest.mark.django_db
def test_work_phase_uses_read_tools(acme, phishing):
    """The model may call a read tool; the loop executes it and feeds the result back."""
    inc = make_incident(acme, subject=phishing)
    make_incident(acme, subject=phishing, state="new")  # another incident to find
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="lookup_incidents", arguments={}, id="c1")]),
        ChatTurn(text="Found a related incident; recommend review."),
    ])
    triage_agent.run_triage_work(inc.id, provider=provider)
    assert provider.calls == 2
    comment = Comment.objects.get(incident=inc, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["tool_trace"][0]["tool"] == "lookup_incidents"


@pytest.mark.django_db
def test_work_phase_runs_once_per_incident(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    triage_agent.run_triage_work(inc.id, provider=FakeProvider([ChatTurn(text="first")]))
    inc.refresh_from_db()
    first_marker = inc.triage_worked_at
    # second call is a no-op (marker set)
    second = FakeProvider([ChatTurn(text="second")])
    triage_agent.run_triage_work(inc.id, provider=second)
    assert second.calls == 0
    inc.refresh_from_db()
    assert inc.triage_worked_at == first_marker
    assert Comment.objects.filter(incident=inc, kind=Comment.KIND_AI_TRIAGE).count() == 1


@pytest.mark.django_db
def test_work_phase_error_hands_off_safely(acme, phishing):
    inc = make_incident(acme, subject=phishing, state="triaged")

    class Boom:
        def chat(self, messages, tools):
            raise RuntimeError("provider down")

    triage_agent.run_triage_work(inc.id, provider=Boom())
    inc.refresh_from_db()
    assert inc.state == Incident.STATE_IN_PROGRESS  # never left stuck
    assert inc.triage_worked_at is not None
    comment = Comment.objects.get(incident=inc, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["error"] is True


# ── executed write tools: apply playbook + work manual tasks (ADR-0025) ───────


# These exercise the orchestrator's per-tool worker thread doing DB writes; run without
# an outer transaction (as the real Celery worker does) so SQLite does not self-lock.
@pytest.mark.django_db(transaction=True)
def test_work_phase_applies_playbook(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    tmpl = TaskTemplate.objects.create(name="Phishing playbook", subject=phishing)
    TaskTemplateItem.objects.create(template=tmpl, title="Check sender", display_order=0)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="apply_task_template",
                                      arguments={"template_id": tmpl.id}, id="c1")]),
        ChatTurn(text="Applied the phishing playbook."),
    ])
    triage_agent.run_triage_work(inc.id, provider=provider)
    assert Task.objects.filter(incident=inc, title="Check sender").exists()


@pytest.mark.django_db
def test_work_phase_rejects_template_of_other_subject(acme, phishing):
    other, _ = Subject.objects.get_or_create(slug="malware", defaults={"name": "Malware"})
    inc = make_incident(acme, subject=phishing)
    tmpl = TaskTemplate.objects.create(name="Malware playbook", subject=other)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="apply_task_template",
                                      arguments={"template_id": tmpl.id}, id="c1")]),
        ChatTurn(text="Could not apply."),
    ])
    triage_agent.run_triage_work(inc.id, provider=provider)
    assert not Task.objects.filter(incident=inc).exists()


@pytest.mark.django_db(transaction=True)
def test_work_phase_records_manual_task_findings_without_closing(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    task = Task.objects.create(incident=inc, title="Investigate sender", task_type=Task.TYPE_MANUAL)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="add_task_comment",
                                      arguments={"task_id": task.id, "text": "Sender domain is 3 days old."},
                                      id="c1")]),
        ChatTurn(text="Recorded findings."),
    ])
    triage_agent.run_triage_work(inc.id, provider=provider)
    task.refresh_from_db()
    assert task.state == Task.STATE_IN_PROGRESS  # progressed, never closed
    assert Comment.objects.filter(incident=inc, task=task, is_internal=True).exists()


@pytest.mark.django_db
def test_triage_write_tools_are_all_authorised():
    """build_triage_tools registers only writes named in the authority module."""
    from incidents.llm.triage_action_authority import TRIAGE_AGENT_WRITE_ACTIONS
    from incidents.llm import triage_tools
    org = Organization.objects.create(name="X", slug="x", wazuh_group="x")
    subj, _ = Subject.objects.get_or_create(slug="phishing", defaults={"name": "Phishing"})
    inc = Incident.objects.create(organization=org, title="t", display_id="INC-X-1", subject=subj)
    tools = triage_tools.build_triage_tools(inc, {"incident": {}}, include_web_search=False)
    write_names = {t.name for t in tools if t.is_write}
    assert write_names == set(TRIAGE_AGENT_WRITE_ACTIONS)


# ── run executable tasks (automated + approved wazuh_response) — ADR-0025 ──────


@pytest.mark.django_db(transaction=True)
def test_work_phase_runs_automated_task(acme, phishing, settings):
    settings.SEMAPHORE_URL = "https://semaphore.example.com"
    settings.SEMAPHORE_API_TOKEN = "t"
    settings.SEMAPHORE_PROJECT_ID = 1
    from automations.models import Automation
    inc = make_incident(acme, subject=phishing)
    automation = Automation.objects.create(name="Scan", semaphore_template_id=7)
    task = Task.objects.create(incident=inc, title="Scan host", task_type=Task.TYPE_AUTOMATED,
                               automation=automation)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="run_task", arguments={"task_id": task.id}, id="c1")]),
        ChatTurn(text="Ran the scan."),
    ])
    mock_client = MagicMock()
    mock_client.launch_job.return_value = 555
    with patch("automations.semaphore.SemaphoreClient", return_value=mock_client):
        triage_agent.run_triage_work(inc.id, provider=provider)
    task.refresh_from_db()
    assert task.state == Task.STATE_IN_PROGRESS
    assert task.semaphore_task_id == 555


def _wazuh_task(inc, approved):
    from automations.models import WazuhActiveResponse
    wr = WazuhActiveResponse.objects.create(
        name="Isolate", command="firewall-drop", autonomous_triage_approved=approved)
    return Task.objects.create(incident=inc, title="Isolate", task_type=Task.TYPE_WAZUH_RESPONSE,
                               wazuh_response=wr)


@pytest.mark.django_db(transaction=True)
def test_work_phase_refuses_unapproved_wazuh_response(acme, phishing):
    from incidents.models import WazuhResponseExecution
    inc = make_incident(acme, subject=phishing)
    task = _wazuh_task(inc, approved=False)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="run_task", arguments={"task_id": task.id}, id="c1")]),
        ChatTurn(text="Recommended isolation for a human."),
    ])
    triage_agent.run_triage_work(inc.id, provider=provider)
    task.refresh_from_db()
    assert task.state == Task.STATE_NEW  # never ran
    assert not WazuhResponseExecution.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_work_phase_runs_approved_wazuh_response(acme, phishing):
    from incidents.models import WazuhResponseExecution
    inc = make_incident(acme, subject=phishing)
    task = _wazuh_task(inc, approved=True)
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="run_task", arguments={"task_id": task.id}, id="c1")]),
        ChatTurn(text="Isolated the host."),
    ])
    mock_client = MagicMock()
    mock_client.run_active_response.return_value = (200, {"ok": True})
    with patch("security.wazuh.WazuhClient", return_value=mock_client):
        triage_agent.run_triage_work(inc.id, provider=provider)
    task.refresh_from_db()
    assert task.state == Task.STATE_DONE
    execution = WazuhResponseExecution.objects.get()
    assert execution.executed_by is None  # autonomous


@pytest.mark.django_db(transaction=True)
def test_work_phase_skips_already_executed_task(acme, phishing):
    inc = make_incident(acme, subject=phishing)
    task = _wazuh_task(inc, approved=True)
    task.state = Task.STATE_DONE
    task.save(update_fields=["state"])
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="run_task", arguments={"task_id": task.id}, id="c1")]),
        ChatTurn(text="Already done."),
    ])
    mock_client = MagicMock()
    with patch("security.wazuh.WazuhClient", return_value=mock_client):
        triage_agent.run_triage_work(inc.id, provider=provider)
    assert not mock_client.run_active_response.called  # no double-fire


# ── the gate is wired into Classify ──────────────────────────────────────────


@pytest.mark.django_db
def test_classify_dispatches_work_on_high_confidence(acme, phishing):
    from incidents.tasks import run_incident_triage
    inc = make_incident(acme, subject=phishing, state="new", severity="medium")
    provider = MagicMock()
    provider.triage_incident.return_value = _result(0.95)
    provider.find_related_incidents.return_value = MagicMock(max_confidence=0.0, related_incident_ids=[])

    with patch("incidents.tasks.get_triage_provider", return_value=provider), \
         patch("incidents.tasks.run_triage_work_task.delay") as mock_delay:
        run_incident_triage.apply(args=[inc.id])

    mock_delay.assert_called_once_with(inc.id)


@pytest.mark.django_db
def test_classify_does_not_dispatch_on_low_confidence(acme, phishing):
    from incidents.tasks import run_incident_triage
    inc = make_incident(acme, subject=phishing, state="new", severity="medium")
    provider = MagicMock()
    provider.triage_incident.return_value = _result(0.1)
    provider.find_related_incidents.return_value = MagicMock(max_confidence=0.0, related_incident_ids=[])

    with patch("incidents.tasks.get_triage_provider", return_value=provider), \
         patch("incidents.tasks.run_triage_work_task.delay") as mock_delay:
        run_incident_triage.apply(args=[inc.id])

    mock_delay.assert_not_called()
