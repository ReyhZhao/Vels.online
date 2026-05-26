import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Asset, Incident, IncidentAsset
from incidents.services.promote import build_promote_payload, find_open_incidents, link_source_assets


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_incident(acme, source_kind="manual", source_ref=None, state="new", display_id=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test",
        display_id=display_id or f"INC-2026-{count + 1:04d}",
        source_kind=source_kind,
        source_ref=source_ref or {},
        state=state,
    )


# ── build_promote_payload ────────────────────────────────────────────────────


def test_wazuh_event_payload_title():
    ref = {"event_id": "abc", "rule_description": "Lateral movement detected", "agent_name": "agent-04", "level": 12}
    payload = build_promote_payload("wazuh_event", ref)
    assert "agent-04" in payload["title"]
    assert "Lateral movement detected" in payload["title"]
    assert payload["severity"] == "critical"
    assert payload["source_kind"] == "wazuh_event"


def test_wazuh_event_severity_levels():
    assert build_promote_payload("wazuh_event", {"level": 12})["severity"] == "critical"
    assert build_promote_payload("wazuh_event", {"level": 9})["severity"] == "high"
    assert build_promote_payload("wazuh_event", {"level": 6})["severity"] == "medium"
    assert build_promote_payload("wazuh_event", {"level": 3})["severity"] == "low"
    assert build_promote_payload("wazuh_event", {"level": 0})["severity"] == "low"


def test_vulnerability_payload_title():
    ref = {"cve_id": "CVE-2025-12345", "cvss_score": 9.8, "description": "Remote code execution flaw."}
    payload = build_promote_payload("vulnerability", ref)
    assert "CVE-2025-12345" in payload["title"]
    assert payload["severity"] == "critical"


def test_vulnerability_cvss_severity():
    assert build_promote_payload("vulnerability", {"cvss_score": 9.0})["severity"] == "critical"
    assert build_promote_payload("vulnerability", {"cvss_score": 7.0})["severity"] == "high"
    assert build_promote_payload("vulnerability", {"cvss_score": 4.0})["severity"] == "medium"
    assert build_promote_payload("vulnerability", {"cvss_score": 1.0})["severity"] == "low"
    assert build_promote_payload("vulnerability", {})["severity"] == "medium"


def test_vulnerability_no_description_uses_cve_id():
    ref = {"cve_id": "CVE-2025-99999", "cvss_score": 7.5}
    payload = build_promote_payload("vulnerability", ref)
    assert payload["title"] == "CVE-2025-99999"


def test_agent_finding_payload_title():
    ref = {"agent_id": "001", "agent_name": "ws-dev-01", "cve_id": "CVE-2025-12345", "cvss_score": 8.0}
    payload = build_promote_payload("agent_finding", ref)
    assert "ws-dev-01" in payload["title"]
    assert "CVE-2025-12345" in payload["title"]
    assert payload["severity"] == "high"


def test_unknown_source_kind_defaults():
    payload = build_promote_payload("manual", {})
    assert payload["title"] == ""
    assert payload["severity"] == "medium"


def test_payload_contains_source_ref():
    ref = {"cve_id": "CVE-2025-12345"}
    payload = build_promote_payload("vulnerability", ref)
    assert payload["source_ref"] == ref


# ── find_open_incidents ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_find_open_incidents_returns_matching(db, acme):
    ref = {"cve_id": "CVE-2025-12345"}
    inc = make_incident(acme, source_kind="vulnerability", source_ref=ref)
    result = find_open_incidents("vulnerability", ref)
    assert any(i.id == inc.id for i in result)


@pytest.mark.django_db
def test_find_open_incidents_excludes_closed(db, acme):
    ref = {"cve_id": "CVE-2025-12345"}
    make_incident(acme, source_kind="vulnerability", source_ref=ref, state="closed")
    result = find_open_incidents("vulnerability", ref)
    assert len(result) == 0


@pytest.mark.django_db
def test_find_open_incidents_ignores_different_source_kind(db, acme):
    ref = {"event_id": "abc"}
    make_incident(acme, source_kind="wazuh_event", source_ref=ref)
    result = find_open_incidents("vulnerability", ref)
    assert len(result) == 0


@pytest.mark.django_db
def test_find_open_incidents_uses_containment(db, acme):
    stored_ref = {"cve_id": "CVE-2025-12345", "cvss_score": 9.8, "description": "Remote code execution."}
    inc = make_incident(acme, source_kind="vulnerability", source_ref=stored_ref)
    result = find_open_incidents("vulnerability", {"cve_id": "CVE-2025-12345"})
    assert any(i.id == inc.id for i in result)


# ── POST /api/incidents/promote/ (two-step) ──────────────────────────────────


@pytest.mark.django_db
def test_promote_form_requires_auth(client, acme):
    response = client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": {"cve_id": "CVE-2025-12345"}},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_promote_form_requires_staff(client, member):
    client.force_login(member)
    response = client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": {"cve_id": "CVE-2025-12345"}},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_promote_form_returns_payload_and_open_incidents(admin_client, acme):
    ref = {"cve_id": "CVE-2025-12345", "cvss_score": 9.8}
    make_incident(acme, source_kind="vulnerability", source_ref=ref)
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": ref},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert "form_payload" in data
    assert "open_incidents" in data
    assert "CVE-2025-12345" in data["form_payload"]["title"]
    assert len(data["open_incidents"]) == 1


@pytest.mark.django_db
def test_promote_form_closed_incidents_not_in_open_list(admin_client, acme):
    ref = {"cve_id": "CVE-2025-12345"}
    make_incident(acme, source_kind="vulnerability", source_ref=ref, state="closed")
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": ref},
        content_type="application/json",
    )
    assert response.json()["open_incidents"] == []


@pytest.mark.django_db
def test_promote_form_missing_source_kind_returns_400(admin_client):
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_ref": {"cve_id": "CVE-2025-12345"}},
        content_type="application/json",
    )
    assert response.status_code == 400


# ── POST /api/incidents/promote/ (commit=true) ───────────────────────────────


@pytest.mark.django_db
def test_promote_commit_creates_incident(admin_client, acme):
    ref = {"cve_id": "CVE-2025-12345", "cvss_score": 9.8}
    response = admin_client.post(
        "/api/incidents/promote/",
        {
            "source_kind": "vulnerability",
            "source_ref": ref,
            "commit": True,
            "org": "acme",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert "CVE-2025-12345" in data["title"]
    assert data["source_kind"] == "vulnerability"
    assert data["source_ref"]["cve_id"] == "CVE-2025-12345"


@pytest.mark.django_db
def test_promote_commit_title_override(admin_client, acme):
    ref = {"cve_id": "CVE-2025-12345"}
    response = admin_client.post(
        "/api/incidents/promote/",
        {
            "source_kind": "vulnerability",
            "source_ref": ref,
            "commit": True,
            "org": "acme",
            "title": "My custom title",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["title"] == "My custom title"


@pytest.mark.django_db
def test_promote_commit_missing_org_returns_400(admin_client):
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": {}, "commit": True},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_promote_commit_nonexistent_org_returns_404(admin_client):
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": {}, "commit": True, "org": "nonexistent"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_promote_wazuh_event_creates_incident(admin_client, acme):
    ref = {"event_id": "e123", "rule_description": "Lateral movement", "agent_name": "ws-01", "level": 12}
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "wazuh_event", "source_ref": ref, "commit": True, "org": "acme"},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_kind"] == "wazuh_event"
    assert data["severity"] == "critical"


# ── GET /api/incidents/?source_ref_contains= ────────────────────────────────


@pytest.mark.django_db
def test_source_ref_contains_filter(client, member, acme):
    ref = {"cve_id": "CVE-2025-12345", "cvss_score": 9.8}
    inc = make_incident(acme, source_kind="vulnerability", source_ref=ref)
    make_incident(acme, source_kind="vulnerability", source_ref={"cve_id": "CVE-2025-99999"})
    client.force_login(member)
    import json
    response = client.get(
        f'/api/incidents/?source_ref_contains={json.dumps({"cve_id": "CVE-2025-12345"})}'
    )
    assert response.status_code == 200
    ids = [i["id"] for i in response.json()["results"]]
    assert inc.id in ids
    assert len(ids) == 1


@pytest.mark.django_db
def test_source_kind_filter(client, member, acme):
    inc = make_incident(acme, source_kind="vulnerability", source_ref={"cve_id": "CVE-2025-12345"})
    make_incident(acme, source_kind="wazuh_event", source_ref={"event_id": "e1"})
    client.force_login(member)
    response = client.get("/api/incidents/?source_kind=vulnerability")
    assert response.status_code == 200
    ids = [i["id"] for i in response.json()["results"]]
    assert inc.id in ids
    assert all(i["source_kind"] == "vulnerability" for i in response.json()["results"])


@pytest.mark.django_db
def test_source_ref_contains_invalid_json_ignored(client, member, acme):
    make_incident(acme)
    client.force_login(member)
    response = client.get("/api/incidents/?source_ref_contains=not-json")
    assert response.status_code == 200


# ── link_source_assets ───────────────────────────────────────────────────────


def make_asset(org, agent_name):
    return Asset.objects.create(
        organization=org,
        kind=Asset.KIND_HOST,
        name=agent_name,
        agent_name=agent_name,
    )


@pytest.mark.django_db
def test_link_source_assets_wazuh_event(acme):
    asset = make_asset(acme, "ws-01")
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "ws-01"})
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc, asset=asset).exists()


@pytest.mark.django_db
def test_link_source_assets_agent_finding(acme):
    asset = make_asset(acme, "db-02")
    inc = make_incident(acme, source_kind="agent_finding", source_ref={"agent_name": "db-02", "cve_id": "CVE-2025-1"})
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc, asset=asset).exists()


@pytest.mark.django_db
def test_link_source_assets_vulnerability_list_of_names(acme):
    a1 = make_asset(acme, "web-01")
    a2 = make_asset(acme, "web-02")
    inc = make_incident(
        acme,
        source_kind="vulnerability",
        source_ref={"cve_id": "CVE-2025-1", "affected_agents": ["web-01", "web-02"]},
    )
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc, asset=a1).exists()
    assert IncidentAsset.objects.filter(incident=inc, asset=a2).exists()


@pytest.mark.django_db
def test_link_source_assets_vulnerability_list_of_dicts(acme):
    asset = make_asset(acme, "web-03")
    inc = make_incident(
        acme,
        source_kind="vulnerability",
        source_ref={"cve_id": "CVE-2025-2", "affected_agents": [{"agent_name": "web-03", "installed_version": "1.0"}]},
    )
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc, asset=asset).exists()


@pytest.mark.django_db
def test_link_source_assets_no_matching_asset_skips_silently(acme):
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "unknown-host"})
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc).count() == 0


@pytest.mark.django_db
def test_link_source_assets_no_agent_name_skips(acme):
    inc = make_incident(acme, source_kind="vulnerability", source_ref={"cve_id": "CVE-2025-3"})
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc).count() == 0


@pytest.mark.django_db
def test_link_source_assets_idempotent(acme):
    asset = make_asset(acme, "ws-04")
    inc = make_incident(acme, source_kind="wazuh_event", source_ref={"agent_name": "ws-04"})
    link_source_assets(inc, acme)
    link_source_assets(inc, acme)
    assert IncidentAsset.objects.filter(incident=inc, asset=asset).count() == 1


@pytest.mark.django_db
def test_promote_commit_links_wazuh_agent_asset(admin_client, acme):
    make_asset(acme, "ws-01")
    ref = {"event_id": "e1", "rule_description": "Brute force", "agent_name": "ws-01", "level": 9}
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "wazuh_event", "source_ref": ref, "commit": True, "org": "acme"},
        content_type="application/json",
    )
    assert response.status_code == 201
    inc = Incident.objects.get(display_id=response.json()["display_id"])
    assert inc.incident_assets.filter(asset__agent_name="ws-01").exists()


@pytest.mark.django_db
def test_promote_commit_links_vulnerability_affected_agents(admin_client, acme):
    make_asset(acme, "web-01")
    make_asset(acme, "web-02")
    ref = {
        "cve_id": "CVE-2025-12345",
        "cvss_score": 9.8,
        "affected_agents": ["web-01", "web-02"],
    }
    response = admin_client.post(
        "/api/incidents/promote/",
        {"source_kind": "vulnerability", "source_ref": ref, "commit": True, "org": "acme"},
        content_type="application/json",
    )
    assert response.status_code == 201
    inc = Incident.objects.get(display_id=response.json()["display_id"])
    linked_names = set(inc.incident_assets.values_list("asset__agent_name", flat=True))
    assert linked_names == {"web-01", "web-02"}
