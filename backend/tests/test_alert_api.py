import pytest
from django.contrib.auth.models import User
from security.models import Organization, OrganizationMembership
from alerts.models import Alert
from incidents.models import Incident


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name="Other", slug="other", wazuh_group="other")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    u = django_user_model.objects.create_user(username="alice", password="pass", is_staff=False)
    return u


@pytest.fixture
def member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


def _wazuh_payload(org="acme", level=6, rule_id="100002", agent_name="web-01"):
    return {
        "source_kind": "wazuh_event",
        "source_ref": {
            "rule_id": rule_id,
            "rule_description": "Lateral movement detected",
            "agent_name": agent_name,
            "level": level,
        },
        "org": org,
    }


# ── POST /api/alerts/ ────────────────────────────────────────────────────────


def test_ingest_creates_alert(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", _wazuh_payload(), content_type="application/json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["display_id"].startswith("AL-")
    assert data["source_kind"] == "wazuh_event"
    assert data["state"] == "new"
    assert "Lateral movement detected" in data["title"]
    assert Alert.objects.filter(display_id=data["display_id"]).exists()


def test_ingest_derives_severity(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", _wazuh_payload(level=12), content_type="application/json")
    assert resp.status_code == 201
    assert resp.json()["severity"] == "critical"


def test_ingest_unauthenticated_returns_401(client, acme):
    resp = client.post("/api/alerts/", _wazuh_payload(), content_type="application/json")
    assert resp.status_code == 401


def test_ingest_non_staff_returns_403(client, member, acme):
    client.force_login(member)
    resp = client.post("/api/alerts/", _wazuh_payload(), content_type="application/json")
    assert resp.status_code == 403


def test_ingest_missing_source_kind_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post(
        "/api/alerts/",
        {"source_ref": {}, "org": "acme"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_ingest_unknown_org_returns_404(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", _wazuh_payload(org="nope"), content_type="application/json")
    assert resp.status_code == 404


def test_ingest_display_id_uses_al_prefix(client, staff_user, acme):
    client.force_login(staff_user)
    for _ in range(3):
        client.post("/api/alerts/", _wazuh_payload(), content_type="application/json")
    ids = list(Alert.objects.values_list("display_id", flat=True))
    assert all(d.startswith("AL-") for d in ids)
    assert len(set(ids)) == 3  # all unique


# ── GET /api/alerts/ ─────────────────────────────────────────────────────────


def test_list_returns_org_scoped_alerts(client, member, acme, other_org):
    Alert.objects.create(
        organization=acme, display_id="AL-0001", source_kind="wazuh_event",
        title="Mine", severity="medium", state="new",
    )
    Alert.objects.create(
        organization=other_org, display_id="AL-0002", source_kind="wazuh_event",
        title="Theirs", severity="medium", state="new",
    )
    client.force_login(member)
    resp = client.get("/api/alerts/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["display_id"] == "AL-0001"


def test_list_unauthenticated_returns_401(client):
    resp = client.get("/api/alerts/")
    assert resp.status_code == 401


def test_list_filter_by_state(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event", title="B", severity="medium", state="ignored")
    client.force_login(member)
    resp = client.get("/api/alerts/?state=new")
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["state"] == "new"


def test_list_filter_by_severity(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="high", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event", title="B", severity="low", state="new")
    client.force_login(member)
    resp = client.get("/api/alerts/?severity=high")
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["severity"] == "high"


def test_list_filter_by_source_kind(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="vulnerability", title="B", severity="medium", state="new")
    client.force_login(member)
    resp = client.get("/api/alerts/?source_kind=vulnerability")
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["source_kind"] == "vulnerability"


def test_list_exclude_state_hides_ignored_by_default(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event", title="B", severity="medium", state="ignored")
    client.force_login(member)
    resp = client.get("/api/alerts/", {"exclude_state": "ignored"})
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["state"] == "new"


def test_list_show_ignored_returns_all(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event", title="B", severity="medium", state="ignored")
    client.force_login(member)
    resp = client.get("/api/alerts/")
    data = resp.json()
    assert data["count"] == 2


def test_list_staff_without_membership_sees_all_alerts(client, staff_user, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    client.force_login(staff_user)
    resp = client.get("/api/alerts/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["display_id"] == "AL-0001"


def test_detail_staff_without_membership_can_get_alert(client, staff_user, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    client.force_login(staff_user)
    resp = client.get("/api/alerts/AL-0001/")
    assert resp.status_code == 200
    assert resp.json()["display_id"] == "AL-0001"


# ── PATCH /api/alerts/<display_id>/ — state transitions ─────────────────────


def test_patch_new_to_acknowledged(client, member, acme):
    a = Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    client.force_login(member)
    resp = client.patch(f"/api/alerts/AL-0001/", {"state": "acknowledged"}, content_type="application/json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "acknowledged"
    assert data["acknowledged_by"] == member.id
    assert data["acknowledged_at"] is not None


def test_patch_new_to_ignored(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"state": "ignored"}, content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["state"] == "ignored"


def test_patch_acknowledged_to_ignored(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="acknowledged")
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"state": "ignored"}, content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["state"] == "ignored"


def test_patch_imported_to_acknowledged_returns_400(client, member, acme):
    inc = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="imported", incident=inc)
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"state": "acknowledged"}, content_type="application/json")
    assert resp.status_code == 400


def test_patch_unauthenticated_returns_401(client, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    resp = client.patch("/api/alerts/AL-0001/", {"state": "acknowledged"}, content_type="application/json")
    assert resp.status_code == 401


# ── PATCH re-link (issue #309) ────────────────────────────────────────────────


def test_patch_relink_imported_alert(client, member, acme):
    inc1 = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I1", severity="medium", state="new")
    inc2 = Incident.objects.create(organization=acme, display_id="INC-2026-0002", title="I2", severity="medium", state="new")
    alert = Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                                 title="A", severity="medium", state="imported", incident=inc1)
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"incident": "INC-2026-0002"}, content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["incident_display_id"] == "INC-2026-0002"


def test_patch_relink_new_alert_returns_400(client, member, acme):
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="new")
    Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I", severity="medium", state="new")
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"incident": "INC-2026-0001"}, content_type="application/json")
    assert resp.status_code == 400


def test_patch_relink_wrong_org_returns_400(client, member, acme, other_org):
    inc1 = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I1", severity="medium", state="new")
    inc_other = Incident.objects.create(organization=other_org, display_id="INC-2026-0099", title="Theirs", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                         title="A", severity="medium", state="imported", incident=inc1)
    client.force_login(member)
    resp = client.patch("/api/alerts/AL-0001/", {"incident": "INC-2026-0099"}, content_type="application/json")
    assert resp.status_code == 400


# ── Bulk promote (issue #308) ─────────────────────────────────────────────────


def test_bulk_promote_creates_incident(client, staff_user, acme):
    client.force_login(staff_user)
    a1 = Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                               source_ref={"agent_name": "web-01", "rule_description": "X", "level": 9},
                               title="A1", severity="high", state="new")
    a2 = Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event",
                               source_ref={"agent_name": "web-01", "rule_description": "Y", "level": 6},
                               title="A2", severity="medium", state="new")
    resp = client.post(
        "/api/alerts/bulk-promote/",
        {"alerts": ["AL-0001", "AL-0002"], "org": "acme"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "display_id" in data  # returns the Incident
    for a in [a1, a2]:
        a.refresh_from_db()
        assert a.state == "imported"
        assert a.incident is not None


def test_bulk_promote_severity_from_highest(client, staff_user, acme):
    client.force_login(staff_user)
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                          source_ref={"agent_name": "web-01", "rule_description": "X", "level": 12},
                          title="A1", severity="critical", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event",
                          source_ref={"agent_name": "web-02", "rule_description": "Y", "level": 3},
                          title="A2", severity="low", state="new")
    resp = client.post(
        "/api/alerts/bulk-promote/",
        {"alerts": ["AL-0001", "AL-0002"], "org": "acme"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    # Incident severity should be derived from the critical alert
    assert resp.json()["severity"] == "critical"


def test_bulk_promote_imported_alert_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    inc = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                          title="A", severity="medium", state="imported", incident=inc)
    resp = client.post(
        "/api/alerts/bulk-promote/",
        {"alerts": ["AL-0001"], "org": "acme"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_bulk_promote_empty_list_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/bulk-promote/", {"alerts": [], "org": "acme"}, content_type="application/json")
    assert resp.status_code == 400


# ── linked_alert_count on incident list ──────────────────────────────────────


def test_incident_list_returns_linked_alert_count(client, member, acme):
    inc = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event", title="A", severity="medium", state="imported", incident=inc)
    Alert.objects.create(organization=acme, display_id="AL-0002", source_kind="wazuh_event", title="B", severity="medium", state="imported", incident=inc)
    client.force_login(member)
    resp = client.get("/api/incidents/")
    assert resp.status_code == 200
    results = resp.json()["results"]
    inc_data = next(r for r in results if r["display_id"] == "INC-2026-0001")
    assert inc_data["linked_alert_count"] == 2


# ── GET /api/incidents/<display_id>/alerts/ ───────────────────────────────────


def test_incident_linked_alerts_endpoint(client, member, acme):
    inc = Incident.objects.create(organization=acme, display_id="INC-2026-0001", title="I", severity="medium", state="new")
    Alert.objects.create(organization=acme, display_id="AL-0001", source_kind="wazuh_event",
                          source_ref={"agent_name": "web-01", "level": 9},
                          title="A", severity="high", state="imported", incident=inc)
    client.force_login(member)
    resp = client.get("/api/incidents/INC-2026-0001/alerts/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["display_id"] == "AL-0001"
    assert data[0]["severity"] == "high"
    assert data[0]["agent_name"] == "web-01"


# ── Workflow / external source kinds and enrichment fields (#325) ────────────


def test_ingest_workflow_alert_with_all_fields(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "workflow",
        "source_ref": {"workflow_id": "wf-001"},
        "org": "acme",
        "title": "Suspicious login from new country",
        "description": "User logged in from IP 1.2.3.4 which geolocates to Russia.",
        "severity": "high",
        "pap": "amber",
        "tlp": "green",
    }, content_type="application/json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Suspicious login from new country"
    assert data["description"] == "User logged in from IP 1.2.3.4 which geolocates to Russia."
    assert data["severity"] == "high"
    assert data["pap"] == "amber"
    assert data["tlp"] == "green"
    assert data["source_kind"] == "workflow"


def test_ingest_external_alert_with_title(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "external",
        "source_ref": {},
        "org": "acme",
        "title": "Alert from SIEM",
    }, content_type="application/json")
    assert resp.status_code == 201
    assert resp.json()["source_kind"] == "external"
    assert resp.json()["title"] == "Alert from SIEM"


def test_ingest_workflow_without_title_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "workflow",
        "source_ref": {},
        "org": "acme",
    }, content_type="application/json")
    assert resp.status_code == 400


def test_ingest_external_without_title_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "external",
        "source_ref": {},
        "org": "acme",
    }, content_type="application/json")
    assert resp.status_code == 400


def test_ingest_invalid_pap_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "workflow",
        "source_ref": {},
        "org": "acme",
        "title": "Test",
        "pap": "purple",
    }, content_type="application/json")
    assert resp.status_code == 400


def test_ingest_invalid_tlp_returns_400(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "workflow",
        "source_ref": {},
        "org": "acme",
        "title": "Test",
        "tlp": "black",
    }, content_type="application/json")
    assert resp.status_code == 400


def test_ingest_api_source_kind_without_title_still_works(client, staff_user, acme):
    """api source_kind retains backwards-compatible optional title."""
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "api",
        "source_ref": {},
        "org": "acme",
    }, content_type="application/json")
    assert resp.status_code == 201


def test_ingest_workflow_omitted_fields_are_null(client, staff_user, acme):
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", {
        "source_kind": "workflow",
        "source_ref": {},
        "org": "acme",
        "title": "Minimal workflow alert",
    }, content_type="application/json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] is None
    assert data["pap"] is None
    assert data["tlp"] is None
    assert data["severity"] is None


def test_ingest_wazuh_alert_derives_severity_as_before(client, staff_user, acme):
    """Platform-native alerts still auto-derive and store severity."""
    client.force_login(staff_user)
    resp = client.post("/api/alerts/", _wazuh_payload(level=14), content_type="application/json")
    assert resp.status_code == 201
    assert resp.json()["severity"] == "critical"
