"""Hunt turn orchestration (module 4, issues #476/#477/#481).

Drives run_hunt_turn with a scripted provider, fake OpenSearch client, and an injected
scope — no LLM, no infra. Asserts the externally observable behaviour: events land on the
persisted log in the ADR-0014 vocabulary, matched docs become Findings, caps are honoured,
an explicit cancel halts the loop, web search is wired in, and the transcript persists.
"""
import pytest

from assistants.orchestrator import LoopCaps
from assistants.tools import ChatTurn, ToolCall
from hunts.models import Hunt, HuntEvent, HuntFinding
from hunts.orchestration import PHASE_SCOPING, run_hunt_turn
from hunts.scope import OrgScope
from security.models import Organization

pytestmark = pytest.mark.django_db


class FakeProvider:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        return self._turns.pop(0) if self._turns else ChatTurn(text="done")


class FakeOS:
    def __init__(self, hits_per_call=None):
        self.calls = []
        self._hits = hits_per_call or []

    def _search(self, index, body):
        i = len(self.calls)
        self.calls.append((index, body))
        return {"hits": {"hits": self._hits[i] if i < len(self._hits) else []}}


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def hunt(org):
    return Hunt.objects.create(title="t", seed_kind="question", seed_text="hunt deadbeef")


def _scope(org):
    return [OrgScope(org.id, org.name, org.wazuh_group, ["1", "2"])]


def _types(hunt):
    return list(HuntEvent.objects.filter(hunt=hunt).order_by("seq").values_list("type", flat=True))


def test_turn_writes_events_records_findings_and_completes(hunt, org):
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="ioc_search",
                                      arguments={"ioc_type": "hash", "value": "deadbeef"}, id="c1")]),
        ChatTurn(text="Found deadbeef on Acme; investigate host."),
    ])
    os_client = FakeOS(hits_per_call=[
        [{"_id": "d1", "_index": "wazuh-alerts", "_source": {"rule": {"description": "malware"}}}],
    ])

    status = run_hunt_turn(hunt, [{"role": "user", "content": "hunt deadbeef"}],
                           provider=provider, scope=_scope(org), os_client=os_client,
                           include_web_search=False)

    assert status == Hunt.STATUS_COMPLETED
    types = _types(hunt)
    assert types[0] == "phase"
    assert "tool" in types
    assert types[-2] == "result"
    assert types[-1] == "done"
    assert HuntFinding.objects.filter(hunt=hunt, organization=org).count() == 1
    hunt.refresh_from_db()
    assert hunt.status == Hunt.STATUS_COMPLETED
    # transcript persisted without the system prompt
    assert hunt.transcript
    assert all(m.get("role") != "system" for m in hunt.transcript)


def test_result_event_carries_proposed_incidents(hunt, org):
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="ioc_search",
                                      arguments={"ioc_type": "ip", "value": "1.2.3.4"}, id="c1")]),
        ChatTurn(text="done"),
    ])
    os_client = FakeOS(hits_per_call=[[{"_id": "x", "_index": "i", "_source": {}}]])

    run_hunt_turn(hunt, [{"role": "user", "content": "q"}], provider=provider,
                  scope=_scope(org), os_client=os_client, include_web_search=False)

    result = HuntEvent.objects.get(hunt=hunt, type="result")
    assert result.data["findings_total"] == 1
    assert result.data["proposed_incidents"][0]["organization_id"] == org.id
    assert result.data["proposed_incidents"][0]["finding_count"] == 1


def test_caps_stop_the_loop(hunt, org):
    # provider always asks for a tool → only max_iterations bounds it
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="ioc_search",
                                      arguments={"ioc_type": "hash", "value": "a"}, id=f"c{i}")])
        for i in range(5)
    ])
    os_client = FakeOS(hits_per_call=[[]] * 5)
    caps = LoopCaps(max_iterations=1, per_tool_timeout_s=5, deadline_s=100, max_auto_actions=8)

    run_hunt_turn(hunt, [{"role": "user", "content": "q"}], provider=provider,
                  scope=_scope(org), os_client=os_client, include_web_search=False, caps=caps)

    assert provider.calls == 1
    result = HuntEvent.objects.get(hunt=hunt, type="result")
    assert result.data["stop_reason"] == "max_iterations"


def test_explicit_cancel_halts_and_marks_cancelled(hunt, org):
    hunt.cancel_requested = True
    hunt.save(update_fields=["cancel_requested"])
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="ioc_search",
                                      arguments={"ioc_type": "hash", "value": "a"}, id="c1")]),
    ])

    status = run_hunt_turn(hunt, [{"role": "user", "content": "q"}], provider=provider,
                           scope=_scope(org), os_client=FakeOS(), include_web_search=False)

    assert status == Hunt.STATUS_CANCELLED
    assert provider.calls == 0  # cancel checked before the first model call
    hunt.refresh_from_db()
    assert hunt.status == Hunt.STATUS_CANCELLED
    assert "done" in _types(hunt)


def test_web_search_tool_is_wired_and_unrestricted(hunt, org):
    searched = []

    def fake_search(query):
        searched.append(query)
        return [{"title": "t", "url": "u", "content": "c"}]

    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="web_search", arguments={"query": "deadbeef malware"}, id="c1")]),
        ChatTurn(text="done"),
    ])

    run_hunt_turn(hunt, [{"role": "user", "content": "q"}], provider=provider,
                  scope=_scope(org), os_client=FakeOS(), include_web_search=True,
                  web_search_fn=fake_search)

    assert searched == ["deadbeef malware"]
    tool_events = HuntEvent.objects.filter(hunt=hunt, type="tool")
    assert any(e.data.get("tool") == "web_search" for e in tool_events)


def test_scoping_turn_commits_no_findings_and_lands_idle(hunt, org):
    # The same IOC sweep that commits a Finding in the searching phase must commit
    # nothing in scoping — the phase boundary is evidence commitment (ADR-0018).
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="ioc_search",
                                      arguments={"ioc_type": "hash", "value": "deadbeef"}, id="c1")]),
        ChatTurn(text="Which orgs do you suspect, and over what window?"),
    ])
    os_client = FakeOS(hits_per_call=[
        [{"_id": "d1", "_index": "wazuh-alerts", "_source": {"rule": {"description": "malware"}}}],
    ])

    status = run_hunt_turn(hunt, [{"role": "user", "content": "hunt deadbeef"}],
                           provider=provider, phase=PHASE_SCOPING, scope=_scope(org),
                           os_client=os_client, include_web_search=False)

    assert status == Hunt.STATUS_SCOPING
    assert HuntFinding.objects.filter(hunt=hunt).count() == 0
    result = HuntEvent.objects.get(hunt=hunt, type="result")
    assert result.data["phase"] == PHASE_SCOPING
    assert result.data["findings_total"] == 0
    hunt.refresh_from_db()
    assert hunt.status == Hunt.STATUS_SCOPING


def test_scoping_turn_can_propose_a_plan(hunt, org):
    provider = FakeProvider([
        ChatTurn(tool_calls=[ToolCall(name="propose_hunt_plan", arguments={
            "refined_question": "Sweep for FIN12 hashes on Windows hosts",
            "hypotheses": ["lateral movement via SMB"],
            "planned_lenses": ["ioc_search", "top_rules"],
            "suggested_scope": {"all_orgs": True, "lookback_days": 14},
        }, id="c1")]),
        ChatTurn(text="Ready when you are."),
    ])

    status = run_hunt_turn(hunt, [{"role": "user", "content": "ransomware?"}],
                           provider=provider, phase=PHASE_SCOPING, scope=_scope(org),
                           os_client=FakeOS(), include_web_search=False)

    assert status == Hunt.STATUS_SCOPING
    hunt.refresh_from_db()
    assert hunt.plan["refined_question"] == "Sweep for FIN12 hashes on Windows hosts"
    assert hunt.plan["suggested_scope"]["lookback_days"] == 14
    # the tool call surfaced on the event log so the UI can light up "Begin hunt"
    assert any(
        e.data.get("tool") == "propose_hunt_plan"
        for e in HuntEvent.objects.filter(hunt=hunt, type="tool")
    )


class CapturingProvider:
    """Records the messages handed to the model so we can assert on the system prompt."""
    def __init__(self):
        self.seen_messages = None

    def chat(self, messages, tools):
        if self.seen_messages is None:
            self.seen_messages = list(messages)
        return ChatTurn(text="done")


@pytest.mark.parametrize("phase", [None, PHASE_SCOPING])
def test_in_scope_asset_inventory_reaches_the_model(hunt, org, phase):
    # #512: the model must be briefed on the customer's own assets in both phases so it
    # doesn't flag our own hosts/IPs as attacker infrastructure.
    scope = [OrgScope(org.id, org.name, org.wazuh_group, ["1"],
                      agents=[{"id": "1", "name": "web01", "ip": "10.0.0.5", "os": "Ubuntu"}])]
    provider = CapturingProvider()

    kwargs = {"phase": phase} if phase else {}
    run_hunt_turn(hunt, [{"role": "user", "content": "q"}], provider=provider,
                  scope=scope, os_client=FakeOS(), include_web_search=False, **kwargs)

    system = next(m for m in provider.seen_messages if m["role"] == "system")
    assert "IN-SCOPE ASSET INVENTORY" in system["content"]
    assert "web01 — 10.0.0.5 — Ubuntu" in system["content"]
    # never persisted into the transcript (system messages are stripped)
    hunt.refresh_from_db()
    assert all(m.get("role") != "system" for m in hunt.transcript)


def test_second_turn_appends_with_higher_turn_and_seq(hunt, org):
    provider1 = FakeProvider([ChatTurn(text="first")])
    run_hunt_turn(hunt, [{"role": "user", "content": "q1"}], provider=provider1,
                  scope=_scope(org), os_client=FakeOS(), include_web_search=False)
    first_max_seq = HuntEvent.objects.filter(hunt=hunt).order_by("-seq").first().seq

    provider2 = FakeProvider([ChatTurn(text="second")])
    run_hunt_turn(hunt, [{"role": "user", "content": "q2"}], provider=provider2,
                  scope=_scope(org), os_client=FakeOS(), include_web_search=False)

    later = HuntEvent.objects.filter(hunt=hunt, seq__gt=first_max_seq)
    assert later.exists()
    assert later.first().turn == 1  # second turn


# ── owner notifications on terminal status (#527) ──────────────────────────────

from notifications.models import Notification, NotificationPreferences  # noqa: E402


class RaisingProvider:
    """A provider whose model call blows up, driving the turn to STATUS_ERROR."""
    def chat(self, messages, tools):
        raise RuntimeError("boom")


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="hunter", password="p")


@pytest.fixture
def owned_hunt(org, owner):
    return Hunt.objects.create(
        title="My hunt", owner=owner, seed_kind="question", seed_text="hunt deadbeef"
    )


def test_completed_hunt_notifies_owner(owned_hunt, owner, org):
    status = run_hunt_turn(owned_hunt, [{"role": "user", "content": "q"}],
                           provider=FakeProvider([ChatTurn(text="done")]),
                           scope=_scope(org), os_client=FakeOS(), include_web_search=False)
    assert status == Hunt.STATUS_COMPLETED
    n = Notification.objects.get(recipient=owner, kind="hunt_complete")
    assert n.payload["link"] == f"/hunting/{owned_hunt.id}"
    assert n.incident_id is None


def test_errored_hunt_notifies_owner(owned_hunt, owner, org):
    status = run_hunt_turn(owned_hunt, [{"role": "user", "content": "q"}],
                           provider=RaisingProvider(),
                           scope=_scope(org), os_client=FakeOS(), include_web_search=False)
    assert status == Hunt.STATUS_ERROR
    n = Notification.objects.get(recipient=owner, kind="hunt_complete")
    assert "error" in n.payload["body"].lower()


def test_completed_hunt_respects_disabled_preference(owned_hunt, owner, org):
    prefs = NotificationPreferences.objects.get_or_create(user=owner)[0]
    prefs.inapp_hunt_complete = False
    prefs.email_hunt_complete = False
    prefs.push_hunt_complete = False
    prefs.save()
    run_hunt_turn(owned_hunt, [{"role": "user", "content": "q"}],
                  provider=FakeProvider([ChatTurn(text="done")]),
                  scope=_scope(org), os_client=FakeOS(), include_web_search=False)
    assert not Notification.objects.filter(recipient=owner, kind="hunt_complete").exists()


def test_ownerless_hunt_completes_without_notification(hunt, org):
    # The default fixture hunt has no owner — completion must neither crash nor notify.
    status = run_hunt_turn(hunt, [{"role": "user", "content": "q"}],
                           provider=FakeProvider([ChatTurn(text="done")]),
                           scope=_scope(org), os_client=FakeOS(), include_web_search=False)
    assert status == Hunt.STATUS_COMPLETED
    assert not Notification.objects.filter(kind="hunt_complete").exists()


def test_scoping_completion_does_not_notify(owned_hunt, owner, org):
    # A scoping turn lands idle (not terminal), so it is not a "hunt finished" event.
    status = run_hunt_turn(owned_hunt, [{"role": "user", "content": "q"}],
                           provider=FakeProvider([ChatTurn(text="let's refine")]),
                           phase=PHASE_SCOPING, scope=_scope(org), os_client=FakeOS(),
                           include_web_search=False)
    assert status == Hunt.STATUS_SCOPING
    assert not Notification.objects.filter(recipient=owner, kind="hunt_complete").exists()
