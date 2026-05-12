import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="pass")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


@pytest.fixture
def assignee(db, django_user_model):
    return django_user_model.objects.create_user(username="assignee", password="pass", is_staff=True)


def make_incident(org, state="new", display_id=None, title="Test"):
    if display_id is None:
        count = Incident.objects.count()
        display_id = f"INC-2026-{count + 1:04d}"
    return Incident.objects.create(
        organization=org, title=title, tlp="amber", display_id=display_id, state=state
    )


# ── auth / permissions ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bulk_requires_auth(client, acme):
    inc = make_incident(acme)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [inc.id], "closure_reason": "resolved"},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_bulk_requires_staff(client, member, acme):
    inc = make_incident(acme)
    client.force_login(member)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [inc.id], "closure_reason": "resolved"},
        content_type="application/json",
    )
    assert response.status_code == 403


# ── validation ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bulk_invalid_action(client, staff, acme):
    inc = make_incident(acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "delete", "ids": [inc.id]},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_bulk_close_missing_closure_reason(client, staff, acme):
    inc = make_incident(acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [inc.id]},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "closure_reason" in response.json()["detail"]


@pytest.mark.django_db
def test_bulk_reassign_missing_assignee_id(client, staff, acme):
    inc = make_incident(acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "reassign", "ids": [inc.id]},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "assignee_id" in response.json()["detail"]


# ── close action ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bulk_close_succeeds(client, staff, acme):
    i1 = make_incident(acme, state="in_progress", display_id="INC-2026-0001")
    i2 = make_incident(acme, state="resolved", display_id="INC-2026-0002")
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [i1.id, i2.id], "closure_reason": "resolved"},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data["succeeded"]) == {i1.id, i2.id}
    assert data["failed"] == []
    i1.refresh_from_db()
    i2.refresh_from_db()
    assert i1.state == "closed"
    assert i2.state == "closed"


@pytest.mark.django_db
def test_bulk_close_already_closed_returns_failure_not_4xx(client, staff, acme):
    i1 = make_incident(acme, state="in_progress", display_id="INC-2026-0010")
    i2 = make_incident(acme, state="closed", display_id="INC-2026-0011")
    i2.closure_reason = "resolved"
    i2.save()
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [i1.id, i2.id], "closure_reason": "false_positive"},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert i1.id in data["succeeded"]
    assert any(f["id"] == i2.id for f in data["failed"])
    assert data["failed"][0]["error"]


@pytest.mark.django_db
def test_bulk_close_records_event(client, staff, acme):
    inc = make_incident(acme, state="in_progress", display_id="INC-2026-0020")
    client.force_login(staff)
    client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [inc.id], "closure_reason": "duplicate"},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=inc, kind="incident_updated").exists()


# ── reassign action ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bulk_reassign_sets_assignee(client, staff, assignee, acme):
    inc = make_incident(acme, display_id="INC-2026-0030")
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "reassign", "ids": [inc.id], "assignee_id": assignee.id},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert inc.id in response.json()["succeeded"]
    inc.refresh_from_db()
    assert inc.assignee_id == assignee.id


@pytest.mark.django_db
def test_bulk_reassign_unassign(client, staff, assignee, acme):
    inc = make_incident(acme, display_id="INC-2026-0031")
    inc.assignee = assignee
    inc.save()
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "reassign", "ids": [inc.id], "assignee_id": None},
        content_type="application/json",
    )
    assert response.status_code == 200
    inc.refresh_from_db()
    assert inc.assignee_id is None


@pytest.mark.django_db
def test_bulk_reassign_records_event(client, staff, assignee, acme):
    inc = make_incident(acme, display_id="INC-2026-0032")
    client.force_login(staff)
    client.post(
        "/api/incidents/bulk/",
        {"action": "reassign", "ids": [inc.id], "assignee_id": assignee.id},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=inc, kind="incident_updated").exists()


# ── org isolation ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bulk_staff_can_act_on_any_org(client, staff, acme, contoso):
    own = make_incident(acme, state="in_progress", display_id="INC-2026-0040")
    other = make_incident(contoso, state="in_progress", display_id="INC-2026-0041")
    client.force_login(staff)
    response = client.post(
        "/api/incidents/bulk/",
        {"action": "close", "ids": [own.id, other.id], "closure_reason": "resolved"},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert own.id in data["succeeded"]
    assert other.id in data["succeeded"]
    assert data["failed"] == []
