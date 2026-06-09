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
