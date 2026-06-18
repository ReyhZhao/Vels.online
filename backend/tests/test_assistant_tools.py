"""Tests for the incident assistant's tools (ADR-0011/0012): scoping + auto-execute.

External-behaviour tests: build the tool set bound to (incident, user), call each
tool's executor, and assert what it returns / mutates / audits.
"""
import pytest

from incidents.models import Incident, IncidentEvent, Comment, Asset, IncidentAsset
from incidents.llm.assistant_tools import build_incident_tools
from incidents.llm import action_authority
from security.models import Organization, OrganizationMembership


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


@pytest.fixture
def org_a(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def org_b(db):
    return Organization.objects.create(name="Beta", slug="beta", wazuh_group="beta")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def member(db, django_user_model, org_a):
    u = django_user_model.objects.create_user(username="m", password="p", is_staff=False)
    OrganizationMembership.objects.create(user=u, organization=org_a)
    return u


@pytest.fixture
def incident(db, org_a):
    return Incident.objects.create(organization=org_a, title="Phish wave", display_id="INC-1", state="new")


def _grounding(incident):
    return {"incident": {"pap": incident.pap}, "iocs": [], "assets": [], "linked_alerts": []}


# ── read-tool scoping ─────────────────────────────────────────────────────────

def test_lookup_incidents_default_narrows_to_org_and_excludes_self(staff, incident, org_a, org_b):
    Incident.objects.create(organization=org_a, title="Phish related", display_id="INC-2", state="new")
    Incident.objects.create(organization=org_b, title="Phish elsewhere", display_id="INC-3", state="new")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_incidents").executor({"query": "phish"})
    ids = {r["display_id"] for r in res.content}
    assert ids == {"INC-2"}                       # same org, excludes self, not org_b


def test_staff_can_widen_lookup_incidents_cross_org(staff, incident, org_a, org_b):
    Incident.objects.create(organization=org_b, title="Phish elsewhere", display_id="INC-3", state="new")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_incidents").executor({"query": "phish", "scope": "all"})
    ids = {r["display_id"] for r in res.content}
    assert "INC-3" in ids                          # cross-org when staff widens


def test_non_staff_cannot_widen_beyond_membership(member, incident, org_a, org_b):
    Incident.objects.create(organization=org_b, title="Phish elsewhere", display_id="INC-3", state="new")
    tools = build_incident_tools(incident, member, _grounding(incident))
    # even asking scope=all, a non-staff member never sees org_b
    res = _tool(tools, "lookup_incidents").executor({"query": "phish", "scope": "all"})
    ids = {r["display_id"] for r in res.content}
    assert "INC-3" not in ids


def test_query_alerts_scoped_to_org(staff, incident, org_a, org_b):
    from alerts.models import Alert
    Alert.objects.create(organization=org_a, display_id="AL-1", source_kind="wazuh_event", title="brute force", state="new")
    Alert.objects.create(organization=org_b, display_id="AL-2", source_kind="wazuh_event", title="brute force", state="new")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "query_alerts").executor({"query": "brute"})
    ids = {r["display_id"] for r in res.content}
    assert ids == {"AL-1"}


def test_lookup_assets_scoped_to_org(staff, incident, org_a, org_b):
    Asset.objects.create(organization=org_a, kind="host", name="WEB-01")
    Asset.objects.create(organization=org_b, kind="host", name="WEB-02")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_assets").executor({"query": "web"})
    names = {r["name"] for r in res.content}
    assert names == {"WEB-01"}


def test_lookup_assets_returns_internet_facing_and_exposures_for_nat_host(staff, incident, org_a):
    from incidents.models import NatExposure
    asset = Asset.objects.create(organization=org_a, kind="host", name="DB-01")
    NatExposure.objects.create(asset=asset, protocol="tcp", port=3389)
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_assets").executor({})
    row = next(r for r in res.content if r["name"] == "DB-01")
    assert row["internet_facing"] is True
    assert len(row["exposures"]) == 1
    exp = row["exposures"][0]
    assert exp["kind"] == "direct_nat"
    assert exp["protection"] == "raw"
    assert exp["specifics"]["port"] == 3389


def test_lookup_assets_returns_empty_exposures_for_unexposed_host(staff, incident, org_a):
    Asset.objects.create(organization=org_a, kind="host", name="INTERNAL-01")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_assets").executor({})
    row = next(r for r in res.content if r["name"] == "INTERNAL-01")
    assert row["internet_facing"] is False
    assert row["exposures"] == []


def test_lookup_assets_returns_ingress_route_exposure(staff, incident, org_a):
    from ingress.models import Route
    asset = Asset.objects.create(organization=org_a, kind="host", name="WEB-FRONT")
    Route.objects.create(
        organization=org_a, fqdn="app.acme.com", backend_host="10.0.0.1",
        backend_port=443, backend_asset=asset,
    )
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "lookup_assets").executor({})
    row = next(r for r in res.content if r["name"] == "WEB-FRONT")
    assert row["internet_facing"] is True
    assert any(e["kind"] == "ingress_route" and e["protection"] == "protected"
               and e["specifics"]["fqdn"] == "app.acme.com"
               for e in row["exposures"])


# ── host_inventory read tool (IT Hygiene Inventory, ADR-0022) ─────────────────

class _FakeWazuh:
    def __init__(self, by_group):
        self.by_group = by_group

    def get_agents(self, group):
        return self.by_group.get(group, [])


class _FakeOS:
    def __init__(self, hits=None):
        self.calls = []
        self._hits = hits or []

    def _search(self, index, body):
        self.calls.append((index, body))
        return {"hits": {"hits": self._hits}}


def _inv_hit(agent_name, pkg):
    return {"_source": {"agent": {"id": "5", "name": agent_name},
                        "package": {"name": pkg, "version": "1.0"}}}


def test_host_inventory_is_org_scoped_and_projects_items(staff, incident, org_a):
    wc = _FakeWazuh({"acme": [{"id": "5", "name": "WEB-01"}]})
    oc = _FakeOS(hits=[_inv_hit("WEB-01", "openssl")])
    tools = build_incident_tools(incident, staff, _grounding(incident), os_client=oc, wazuh_client=wc)

    res = _tool(tools, "host_inventory").executor({"agent_name": "WEB-01", "kind": "software"})

    assert res.error is None
    # queried the packages index, scoped to the resolved host's agent id only
    assert oc.calls[0][0] == "wazuh-states-inventory-packages-*"
    assert oc.calls[0][1]["query"]["bool"]["filter"][0]["terms"]["agent.id"] == ["5"]
    assert res.content["items"] == [{"agent_id": "5", "agent_name": "WEB-01",
                                     "name": "openssl", "version": "1.0",
                                     "vendor": None, "architecture": None}]


def test_host_inventory_cannot_reach_a_host_in_another_org(staff, incident, org_a, org_b):
    # WEB-99 lives in beta; the incident is in acme -> the tool only ever queries acme
    wc = _FakeWazuh({"acme": [{"id": "5", "name": "WEB-01"}],
                     "beta": [{"id": "99", "name": "WEB-99"}]})
    oc = _FakeOS()
    tools = build_incident_tools(incident, staff, _grounding(incident), os_client=oc, wazuh_client=wc)

    res = _tool(tools, "host_inventory").executor({"agent_name": "WEB-99", "kind": "software"})

    assert res.error is not None          # not resolvable within the incident's org
    assert oc.calls == []                 # the inventory index is never queried


def test_host_inventory_unknown_host_returns_clean_error(staff, incident, org_a):
    wc = _FakeWazuh({"acme": [{"id": "5", "name": "WEB-01"}]})
    oc = _FakeOS()
    tools = build_incident_tools(incident, staff, _grounding(incident), os_client=oc, wazuh_client=wc)

    res = _tool(tools, "host_inventory").executor({"agent_name": "GHOST", "kind": "software"})

    assert res.error is not None and "this organisation" in res.error
    assert oc.calls == []


def test_host_inventory_rejects_bad_kind(staff, incident, org_a):
    tools = build_incident_tools(incident, staff, _grounding(incident),
                                 os_client=_FakeOS(), wazuh_client=_FakeWazuh({}))
    res = _tool(tools, "host_inventory").executor({"agent_name": "WEB-01", "kind": "packages"})
    assert res.error is not None


def test_host_inventory_is_a_read_tool_no_scope_all_widen(staff, incident, org_a):
    tools = build_incident_tools(incident, staff, _grounding(incident),
                                 os_client=_FakeOS(), wazuh_client=_FakeWazuh({}))
    inv = _tool(tools, "host_inventory")
    assert inv.is_write is False
    assert "scope" not in inv.parameters["properties"]   # no staff fleet-wide widen


# ── auto-execute write tools (ADR-0012) ───────────────────────────────────────

def test_add_internal_comment_creates_internal_comment_and_audits(staff, incident):
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_internal_comment").executor({"text": "looks like a campaign"})
    assert res.error is None
    c = Comment.objects.get(incident=incident)
    assert c.is_internal is True and c.body == "looks like a campaign"
    ev = IncidentEvent.objects.get(incident=incident, kind="assistant_action")
    assert ev.payload["autonomous"] is True
    assert ev.payload["action_type"] == "add_internal_comment"


def test_self_assign_sets_assignee_and_audits(staff, incident):
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "self_assign").executor({})
    incident.refresh_from_db()
    assert incident.assignee_id == staff.id
    assert IncidentEvent.objects.filter(incident=incident, kind="assistant_action").exists()
    assert res.error is None


def test_add_tag_appends_and_dedupes(staff, incident):
    tools = build_incident_tools(incident, staff, _grounding(incident))
    _tool(tools, "add_tag").executor({"tag": "phishing"})
    incident.refresh_from_db()
    assert incident.tags == ["phishing"]
    # duplicate is a no-op, no second audit event
    _tool(tools, "add_tag").executor({"tag": "phishing"})
    incident.refresh_from_db()
    assert incident.tags == ["phishing"]
    assert IncidentEvent.objects.filter(incident=incident, kind="assistant_action").count() == 1


def test_link_known_asset_links_org_asset_only(staff, incident, org_a, org_b):
    a = Asset.objects.create(organization=org_a, kind="host", name="DB-01")
    foreign = Asset.objects.create(organization=org_b, kind="host", name="DB-02")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "link_known_asset").executor({"asset_id": a.id})
    assert res.error is None
    assert IncidentAsset.objects.filter(incident=incident, asset=a).exists()
    # an asset from another org cannot be linked
    res2 = _tool(tools, "link_known_asset").executor({"asset_id": foreign.id})
    assert res2.error is not None
    assert not IncidentAsset.objects.filter(incident=incident, asset=foreign).exists()


def test_write_tools_marked_is_write_reads_not(staff, incident):
    tools = build_incident_tools(incident, staff, _grounding(incident))
    writes = {t.name for t in tools if t.is_write}
    assert writes == {"add_internal_comment", "add_task_comment", "self_assign", "add_tag", "link_known_asset"}
    reads = {t.name for t in tools if not t.is_write}
    assert {"lookup_incidents", "query_alerts", "lookup_assets"} <= reads


# ── add_task_comment (works manual tasks, ADR-0013) ───────────────────────────

def _manual_task(incident, **kw):
    from incidents.models import Task
    return Task.objects.create(incident=incident, title=kw.pop("title", "Check sender domain"),
                               task_type=Task.TYPE_MANUAL, **kw)


def test_add_task_comment_records_internal_task_scoped_comment_and_audits(staff, incident):
    task = _manual_task(incident)
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_task_comment").executor({"task_id": task.id, "text": "domain is 3 days old"})
    assert res.error is None
    c = Comment.objects.get(task=task)
    assert c.task_id == task.id and c.incident_id == incident.id
    assert c.is_internal is True and c.body == "domain is 3 days old"
    ev = IncidentEvent.objects.get(incident=incident, kind="assistant_action")
    assert ev.payload["autonomous"] is True and ev.payload["action_type"] == "add_task_comment"
    assert ev.payload["detail"]["task_id"] == task.id


def test_add_task_comment_advances_new_task_to_in_progress(staff, incident):
    from incidents.models import Task
    task = _manual_task(incident)
    assert task.state == Task.STATE_NEW
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_task_comment").executor({"task_id": task.id, "text": "looked into it"})
    assert res.error is None
    task.refresh_from_db()
    assert task.state == Task.STATE_IN_PROGRESS
    assert task.closed_at is None
    ev = IncidentEvent.objects.get(incident=incident, kind="task_state_changed")
    assert ev.payload["task_id"] == task.id
    assert ev.payload["old"] == Task.STATE_NEW and ev.payload["new"] == Task.STATE_IN_PROGRESS


def test_add_task_comment_does_not_close_or_re_transition_worked_task(staff, incident):
    from incidents.models import Task
    for start in (Task.STATE_IN_PROGRESS, Task.STATE_DONE, Task.STATE_CANCELLED):
        task = _manual_task(incident, title=f"t-{start}", state=start)
        tools = build_incident_tools(incident, staff, _grounding(incident))
        res = _tool(tools, "add_task_comment").executor({"task_id": task.id, "text": "more"})
        assert res.error is None
        task.refresh_from_db()
        assert task.state == start  # never advanced, never closed/cancelled
        assert not IncidentEvent.objects.filter(
            incident=incident, kind="task_state_changed", payload__task_id=task.id).exists()


def test_add_task_comment_rejects_automated_task(staff, incident):
    from incidents.models import Task
    task = Task.objects.create(incident=incident, title="Run playbook", task_type=Task.TYPE_AUTOMATED)
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_task_comment").executor({"task_id": task.id, "text": "x"})
    assert res.error is not None
    assert not Comment.objects.filter(task=task).exists()


def test_add_task_comment_rejects_wazuh_response_task(staff, incident):
    from incidents.models import Task
    task = Task.objects.create(incident=incident, title="Isolate host", task_type=Task.TYPE_WAZUH_RESPONSE)
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_task_comment").executor({"task_id": task.id, "text": "x"})
    assert res.error is not None
    assert not Comment.objects.filter(task=task).exists()


def test_add_task_comment_rejects_task_from_another_incident(staff, incident, org_a):
    other = Incident.objects.create(organization=org_a, title="Other", display_id="INC-9", state="new")
    foreign_task = _manual_task(other, title="Foreign manual task")
    tools = build_incident_tools(incident, staff, _grounding(incident))
    res = _tool(tools, "add_task_comment").executor({"task_id": foreign_task.id, "text": "x"})
    assert res.error is not None
    assert not Comment.objects.filter(task=foreign_task).exists()


def test_task_workable_by_assistant_predicate(staff, incident, org_a):
    from incidents.models import Task
    from incidents.llm.action_authority import task_workable_by_assistant
    manual = _manual_task(incident)
    automated = Task.objects.create(incident=incident, title="auto", task_type=Task.TYPE_AUTOMATED)
    wazuh = Task.objects.create(incident=incident, title="wz", task_type=Task.TYPE_WAZUH_RESPONSE)
    other = Incident.objects.create(organization=org_a, title="Other", display_id="INC-8", state="new")
    foreign = _manual_task(other, title="foreign")
    assert task_workable_by_assistant(manual, incident) is True
    assert task_workable_by_assistant(automated, incident) is False
    assert task_workable_by_assistant(wazuh, incident) is False
    assert task_workable_by_assistant(foreign, incident) is False
    assert task_workable_by_assistant(None, incident) is False


# ── action authority split ──────────────────────────────────────────────────

def test_action_authority_split():
    for a in ("add_internal_comment", "add_task_comment", "self_assign", "add_tag", "link_known_asset"):
        assert action_authority.is_auto_executable(a)
        assert not action_authority.is_proposable(a)
    for a in ("transition_state", "update_field", "apply_task_template",
              "send_contact_message", "create_exception", "close"):
        assert action_authority.is_proposable(a)
        assert not action_authority.is_auto_executable(a)
