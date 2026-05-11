import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent
from incidents.services.events import record_event
from incidents.services.visibility import filter_events_for_user


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="pass")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


@pytest.fixture
def outsider(db, django_user_model):
    return django_user_model.objects.create_user(username="outsider", password="pass")


def make_incident(org, tlp="green"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org, title="Test", display_id=f"INC-2026-{count + 1:04d}", tlp=tlp
    )


# ── filter_events_for_user ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_staff_sees_all_events_including_internal(acme, staff):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "comment_added", payload={"is_internal": True})
    record_event(incident, "incident_created")
    qs = IncidentEvent.objects.filter(incident=incident)
    result = filter_events_for_user(qs, staff, incident)
    assert result.count() == 2


@pytest.mark.django_db
def test_member_at_green_excludes_internal_events(acme, member):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "comment_added", payload={"is_internal": True})
    record_event(incident, "incident_created")
    qs = IncidentEvent.objects.filter(incident=incident)
    result = filter_events_for_user(qs, member, incident)
    assert result.count() == 1
    assert result.first().kind == "incident_created"


@pytest.mark.django_db
def test_member_at_white_excludes_internal_events(acme, member):
    incident = make_incident(acme, tlp="white")
    record_event(incident, "comment_added", payload={"is_internal": True})
    record_event(incident, "incident_created")
    qs = IncidentEvent.objects.filter(incident=incident)
    result = filter_events_for_user(qs, member, incident)
    assert result.count() == 1


@pytest.mark.django_db
def test_member_at_amber_sees_no_events(acme, member):
    incident = make_incident(acme, tlp="amber")
    record_event(incident, "incident_created")
    qs = IncidentEvent.objects.filter(incident=incident)
    result = filter_events_for_user(qs, member, incident)
    assert result.count() == 0


@pytest.mark.django_db
def test_outsider_sees_no_events(acme, outsider):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "incident_created")
    qs = IncidentEvent.objects.filter(incident=incident)
    result = filter_events_for_user(qs, outsider, incident)
    assert result.count() == 0


# ── timeline endpoint ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_timeline_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_timeline_returns_events_in_order(client, acme, staff):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "incident_created")
    record_event(incident, "incident_updated", payload={"changes": {"state": {"old": "new", "new": "triaged"}}})
    record_event(incident, "comment_added", payload={"is_internal": False})
    client.force_login(staff)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert results[0]["kind"] == "incident_created"
    assert results[1]["kind"] == "incident_updated"
    assert results[2]["kind"] == "comment_added"


@pytest.mark.django_db
def test_timeline_staff_sees_internal_events(client, acme, staff):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "comment_added", payload={"is_internal": True})
    client.force_login(staff)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.django_db
def test_timeline_member_at_green_excludes_internal(client, acme, member):
    incident = make_incident(acme, tlp="green")
    record_event(incident, "comment_added", payload={"is_internal": True})
    record_event(incident, "incident_created")
    client.force_login(member)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["kind"] == "incident_created"


@pytest.mark.django_db
def test_timeline_member_at_amber_returns_403(client, acme, member):
    incident = make_incident(acme, tlp="amber")
    client.force_login(member)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_timeline_outsider_returns_404(client, acme, outsider):
    incident = make_incident(acme, tlp="green")
    client.force_login(outsider)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_timeline_pagination(client, acme, staff):
    incident = make_incident(acme, tlp="green")
    for i in range(55):
        record_event(incident, "incident_created")
    client.force_login(staff)
    response = client.get(f"/api/incidents/{incident.display_id}/timeline/")
    data = response.json()
    assert data["count"] == 55
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert len(data["results"]) == 50

    response2 = client.get(f"/api/incidents/{incident.display_id}/timeline/?page=2")
    data2 = response2.json()
    assert data2["page"] == 2
    assert len(data2["results"]) == 5


@pytest.mark.django_db
def test_timeline_returns_404_for_unknown_incident(client, staff):
    client.force_login(staff)
    response = client.get("/api/incidents/INC-DOES-NOT-EXIST/timeline/")
    assert response.status_code == 404
