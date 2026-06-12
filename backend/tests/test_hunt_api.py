"""Threat Hunting REST API (issues #476/#478/#481/#482/#484).

End-to-end through the views: staff-gating, create (question + SSRF-guarded URL seed),
list/review, follow-up turn, cancel, and confirm-incident. The Celery dispatch is patched
so the turn itself is exercised by test_hunt_orchestration, not here.
"""
import pytest

from hunts.models import Hunt, HuntFinding
from incidents.models import Incident
from security.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="bob", password="pass", is_staff=False)


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    kicked = []
    monkeypatch.setattr("hunts.views._kick_turn", lambda hunt, messages: kicked.append((hunt, messages)))
    return kicked


def test_create_question_hunt(client, staff_user, no_celery):
    client.force_login(staff_user)
    resp = client.post("/api/hunts/", {
        "seed_kind": "question", "seed_text": "hunt for deadbeef", "scope_all_orgs": True,
    }, content_type="application/json")
    assert resp.status_code == 201
    hunt = Hunt.objects.get()
    assert hunt.seed_text == "hunt for deadbeef"
    assert hunt.status == Hunt.STATUS_CREATED
    assert hunt.transcript == [{"role": "user", "content": "hunt for deadbeef"}]
    assert len(no_celery) == 1  # a turn was dispatched


def test_create_rejects_non_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.post("/api/hunts/", {"seed_kind": "question", "seed_text": "x"},
                       content_type="application/json")
    assert resp.status_code == 403
    assert Hunt.objects.count() == 0


def test_create_url_seed_fetches_report_behind_ssrf_guard(client, staff_user, monkeypatch):
    monkeypatch.setattr("hunts.report_fetch.fetch_report", lambda url, **kw: "REPORT: ioc deadbeef")
    client.force_login(staff_user)
    resp = client.post("/api/hunts/", {
        "seed_kind": "url", "seed_url": "https://intel.example.com/report",
    }, content_type="application/json")
    assert resp.status_code == 201
    hunt = Hunt.objects.get()
    assert "REPORT: ioc deadbeef" in hunt.seed_text
    assert hunt.seed_url == "https://intel.example.com/report"


def test_create_narrow_scope_requires_orgs(client, staff_user):
    client.force_login(staff_user)
    resp = client.post("/api/hunts/", {
        "seed_kind": "question", "seed_text": "x", "scope_all_orgs": False, "scope_org_ids": [],
    }, content_type="application/json")
    assert resp.status_code == 400


def test_create_with_narrow_scope_sets_orgs(client, staff_user, org):
    client.force_login(staff_user)
    resp = client.post("/api/hunts/", {
        "seed_kind": "question", "seed_text": "x", "scope_all_orgs": False,
        "scope_org_ids": [org.id], "lookback_days": 7,
    }, content_type="application/json")
    assert resp.status_code == 201
    hunt = Hunt.objects.get()
    assert hunt.scope_all_orgs is False
    assert list(hunt.scope_orgs.all()) == [org]
    assert hunt.lookback_days == 7


def test_list_hunts_staff_only(client, staff_user, regular_user):
    Hunt.objects.create(title="h1", seed_text="q")
    client.force_login(regular_user)
    assert client.get("/api/hunts/").status_code == 403
    client.force_login(staff_user)
    resp = client.get("/api/hunts/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_detail_returns_findings_and_proposals(client, staff_user, org):
    hunt = Hunt.objects.create(title="h", seed_text="q")
    HuntFinding.objects.create(hunt=hunt, organization=org, source_index="i", wazuh_doc_id="1",
                               raw_doc={}, summary="s")
    client.force_login(staff_user)
    resp = client.get(f"/api/hunts/{hunt.id}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["finding_count"] == 1
    assert body["proposed_incidents"][0]["organization_id"] == org.id


def test_cancel_sets_flag(client, staff_user):
    hunt = Hunt.objects.create(title="h", seed_text="q", status=Hunt.STATUS_RUNNING)
    client.force_login(staff_user)
    resp = client.post(f"/api/hunts/{hunt.id}/cancel/")
    assert resp.status_code == 202
    hunt.refresh_from_db()
    assert hunt.cancel_requested is True


def test_follow_up_turn_appends_message(client, staff_user, no_celery):
    hunt = Hunt.objects.create(title="h", seed_text="q",
                               transcript=[{"role": "user", "content": "first"}],
                               status=Hunt.STATUS_COMPLETED)
    client.force_login(staff_user)
    resp = client.post(f"/api/hunts/{hunt.id}/turn/", {"message": "dig deeper"},
                       content_type="application/json")
    assert resp.status_code == 202
    hunt.refresh_from_db()
    assert hunt.transcript[-1] == {"role": "user", "content": "dig deeper"}
    assert len(no_celery) == 1


def test_confirm_incident_materialises_for_org(client, staff_user, org):
    hunt = Hunt.objects.create(title="h", seed_text="q")
    HuntFinding.objects.create(hunt=hunt, organization=org, source_index="i", wazuh_doc_id="1",
                               raw_doc={"agent": {"name": "host"}}, summary="s")
    client.force_login(staff_user)
    resp = client.post(f"/api/hunts/{hunt.id}/confirm-incident/", {"organization_id": org.id},
                       content_type="application/json")
    assert resp.status_code == 201
    display_id = resp.json()["incident_display_id"]
    inc = Incident.objects.get(display_id=display_id)
    assert inc.organization == org
    assert inc.source_kind == Incident.SOURCE_THREAT_HUNT
