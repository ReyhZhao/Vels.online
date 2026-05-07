import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_incident(org, tlp="amber", title="Test Incident", display_id=None):
    if display_id is None:
        count = Incident.objects.count()
        display_id = f"INC-2026-{count + 1:04d}"
    return Incident.objects.create(organization=org, title=title, tlp=tlp, display_id=display_id)


# ── GET /api/incidents/ ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client):
    response = client.get("/api/incidents/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_list_returns_own_org_incidents(client, acme_member, acme, contoso):
    own = make_incident(acme, tlp="amber")
    other = make_incident(contoso, tlp="green")
    client.force_login(acme_member)
    response = client.get("/api/incidents/")
    assert response.status_code == 200
    ids = [i["id"] for i in response.json()]
    assert own.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_list_hides_tlp_red_from_members(client, acme_member, acme):
    visible = make_incident(acme, tlp="amber")
    hidden = make_incident(acme, tlp="red")
    client.force_login(acme_member)
    response = client.get("/api/incidents/")
    ids = [i["id"] for i in response.json()]
    assert visible.id in ids
    assert hidden.id not in ids


@pytest.mark.django_db
def test_list_staff_sees_all(admin_client, acme, contoso):
    i1 = make_incident(acme, tlp="red")
    i2 = make_incident(contoso, tlp="amber")
    response = admin_client.get("/api/incidents/")
    assert response.status_code == 200
    ids = [i["id"] for i in response.json()]
    assert i1.id in ids
    assert i2.id in ids


# ── POST /api/incidents/ ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_requires_auth(client, acme):
    response = client.post(
        "/api/incidents/",
        {"org": "acme", "title": "New incident"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_create_non_staff_forbidden(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.post(
        "/api/incidents/",
        {"org": "acme", "title": "New"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_staff_creates_incident(admin_client, acme):
    response = admin_client.post(
        "/api/incidents/",
        {"org": "acme", "title": "Breach detected", "severity": "high", "tlp": "amber", "pap": "amber"},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Breach detected"
    assert data["display_id"].startswith("INC-")
    assert data["org_slug"] == "acme"


@pytest.mark.django_db
def test_create_writes_incident_created_event(admin_client, acme):
    admin_client.post(
        "/api/incidents/",
        {"org": "acme", "title": "Test"},
        content_type="application/json",
    )
    incident = Incident.objects.get(organization=acme)
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_created").exists()


@pytest.mark.django_db
def test_create_missing_org_returns_400(admin_client):
    response = admin_client.post(
        "/api/incidents/",
        {"title": "No org"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_unknown_org_returns_404(admin_client):
    response = admin_client.post(
        "/api/incidents/",
        {"org": "nonexistent", "title": "Test"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_create_missing_title_returns_400(admin_client, acme):
    response = admin_client.post(
        "/api/incidents/",
        {"org": "acme"},
        content_type="application/json",
    )
    assert response.status_code == 400


# ── GET /api/incidents/<id>/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_detail_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_detail_member_can_view_own_org(client, acme_member, acme):
    incident = make_incident(acme, tlp="amber")
    client.force_login(acme_member)
    response = client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 200
    assert response.json()["id"] == incident.id


@pytest.mark.django_db
def test_detail_member_cannot_view_tlp_red(client, acme_member, acme):
    incident = make_incident(acme, tlp="red")
    client.force_login(acme_member)
    response = client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_member_cannot_view_other_org(client, acme_member, contoso):
    incident = make_incident(contoso)
    client.force_login(acme_member)
    response = client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_staff_can_view_red(admin_client, acme):
    incident = make_incident(acme, tlp="red")
    response = admin_client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_detail_not_found_returns_404(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/incidents/99999/")
    assert response.status_code == 404


# ── PATCH /api/incidents/<id>/ ───────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.patch(
        f"/api/incidents/{incident.id}/",
        {"title": "Updated"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_patch_member_can_update_own_incident(client, acme_member, acme):
    incident = make_incident(acme, tlp="amber")
    client.force_login(acme_member)
    response = client.patch(
        f"/api/incidents/{incident.id}/",
        {"title": "Updated Title"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.django_db
def test_patch_writes_incident_updated_event(client, acme_member, acme):
    incident = make_incident(acme, tlp="amber")
    client.force_login(acme_member)
    client.patch(
        f"/api/incidents/{incident.id}/",
        {"title": "Changed"},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_updated").exists()


@pytest.mark.django_db
def test_patch_event_payload_contains_changes(client, acme_member, acme):
    incident = make_incident(acme, tlp="amber", title="Original")
    client.force_login(acme_member)
    client.patch(
        f"/api/incidents/{incident.id}/",
        {"title": "New Title"},
        content_type="application/json",
    )
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["title"]["old"] == "Original"
    assert event.payload["changes"]["title"]["new"] == "New Title"


@pytest.mark.django_db
def test_patch_non_member_forbidden(client, alice, acme):
    incident = make_incident(acme)
    client.force_login(alice)
    response = client.patch(
        f"/api/incidents/{incident.id}/",
        {"title": "Hacked"},
        content_type="application/json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_patch_staff_can_update_any(admin_client, acme):
    incident = make_incident(acme, tlp="red")
    response = admin_client.patch(
        f"/api/incidents/{incident.id}/",
        {"severity": "critical"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "critical"
