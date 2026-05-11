import pytest
from django.core.exceptions import ValidationError
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent
from incidents.services.transfer import transfer_incident


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff_actor(db, django_user_model):
    return django_user_model.objects.create_user(username="actor", password="pass", is_staff=True)


@pytest.fixture
def staff_target(db, django_user_model):
    return django_user_model.objects.create_user(username="target", password="pass", is_staff=True)


@pytest.fixture
def non_staff(db, django_user_model):
    return django_user_model.objects.create_user(username="regular", password="pass", is_staff=False)


def make_incident(org, assignee=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        assignee=assignee,
    )


# ── service unit tests ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_transfer_changes_assignee(acme, staff_actor, staff_target):
    incident = make_incident(acme, assignee=staff_actor)
    transfer_incident(incident, staff_target, actor=staff_actor)
    incident.refresh_from_db()
    assert incident.assignee_id == staff_target.id


@pytest.mark.django_db
def test_transfer_writes_event_with_from_to(acme, staff_actor, staff_target):
    incident = make_incident(acme, assignee=staff_actor)
    old_id = staff_actor.id
    transfer_incident(incident, staff_target, actor=staff_actor)
    event = IncidentEvent.objects.get(incident=incident, kind="incident_assignee_changed")
    assert event.payload["from"] == old_id
    assert event.payload["to"] == staff_target.id
    assert event.actor_id == staff_actor.id


@pytest.mark.django_db
def test_transfer_rejects_non_staff_target(acme, staff_actor, non_staff):
    incident = make_incident(acme, assignee=staff_actor)
    with pytest.raises(ValidationError):
        transfer_incident(incident, non_staff, actor=staff_actor)


@pytest.mark.django_db
def test_transfer_from_no_assignee_records_null_from(acme, staff_actor, staff_target):
    incident = make_incident(acme, assignee=None)
    transfer_incident(incident, staff_target, actor=staff_actor)
    event = IncidentEvent.objects.get(incident=incident, kind="incident_assignee_changed")
    assert event.payload["from"] is None
    assert event.payload["to"] == staff_target.id


# ── endpoint tests ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_transfer_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.post(f"/api/incidents/{incident.display_id}/transfer/", {"assignee_id": 1}, content_type="application/json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_transfer_endpoint_requires_staff(client, acme, non_staff):
    incident = make_incident(acme)
    client.force_login(non_staff)
    response = client.post(f"/api/incidents/{incident.display_id}/transfer/", {"assignee_id": 1}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_transfer_endpoint_succeeds_for_staff_target(client, acme, staff_actor, staff_target):
    incident = make_incident(acme, assignee=staff_actor)
    client.force_login(staff_actor)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transfer/",
        {"assignee_id": staff_target.id},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["assignee"] == staff_target.id


@pytest.mark.django_db
def test_transfer_endpoint_rejects_non_staff_target(client, acme, staff_actor, non_staff):
    incident = make_incident(acme, assignee=staff_actor)
    client.force_login(staff_actor)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transfer/",
        {"assignee_id": non_staff.id},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_transfer_endpoint_rejects_nonexistent_user(client, acme, staff_actor):
    incident = make_incident(acme, assignee=staff_actor)
    client.force_login(staff_actor)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transfer/",
        {"assignee_id": 99999},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_transfer_endpoint_returns_404_for_missing_incident(client, staff_actor):
    client.force_login(staff_actor)
    response = client.post("/api/incidents/INC-DOES-NOT-EXIST/transfer/", {"assignee_id": staff_actor.id}, content_type="application/json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_staff_user_list_returns_staff_only(client, staff_actor, non_staff):
    client.force_login(non_staff)
    response = client.get("/api/incidents/staff-users/")
    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()]
    assert staff_actor.username in usernames
    assert non_staff.username not in usernames
