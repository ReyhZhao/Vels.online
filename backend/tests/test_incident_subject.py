import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent, Subject


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


@pytest.fixture
def malware(db):
    return Subject.objects.get(slug="malware")


def make_incident(acme, state="new", subject=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
        subject=subject,
    )


def patch_incident(client, incident, data):
    return client.patch(
        f"/api/incidents/{incident.display_id}/",
        data,
        content_type="application/json",
    )


# ── subject lock rule ────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["new", "triaged"])
def test_subject_settable_in_triage_states(state, client, acme_member, acme, phishing):
    incident = make_incident(acme, state=state)
    client.force_login(acme_member)
    response = patch_incident(client, incident, {"subject": phishing.id})
    assert response.status_code == 200
    incident.refresh_from_db()
    assert incident.subject == phishing


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["in_progress", "on_hold", "resolved", "closed"])
def test_subject_locked_after_triage(state, client, acme_member, acme, phishing):
    incident = make_incident(acme, state=state)
    client.force_login(acme_member)
    response = patch_incident(client, incident, {"subject": phishing.id})
    assert response.status_code == 400
    assert "subject" in response.json()["detail"].lower() or "triage" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_subject_clearable_in_triage(client, acme_member, acme, phishing):
    incident = make_incident(acme, state="new", subject=phishing)
    client.force_login(acme_member)
    response = patch_incident(client, incident, {"subject": None})
    assert response.status_code == 200
    incident.refresh_from_db()
    assert incident.subject is None


# ── subject change event ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_subject_set_writes_event(client, acme_member, acme, phishing):
    incident = make_incident(acme, state="new")
    client.force_login(acme_member)
    patch_incident(client, incident, {"subject": phishing.id})
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["subject"]["old"] is None
    assert event.payload["changes"]["subject"]["new"] == "phishing"


@pytest.mark.django_db
def test_subject_changed_writes_event(client, acme_member, acme, phishing, malware):
    incident = make_incident(acme, state="new", subject=phishing)
    client.force_login(acme_member)
    patch_incident(client, incident, {"subject": malware.id})
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["subject"]["old"] == "phishing"
    assert event.payload["changes"]["subject"]["new"] == "malware"


@pytest.mark.django_db
def test_subject_cleared_writes_event(client, acme_member, acme, phishing):
    incident = make_incident(acme, state="new", subject=phishing)
    client.force_login(acme_member)
    patch_incident(client, incident, {"subject": None})
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["subject"]["old"] == "phishing"
    assert event.payload["changes"]["subject"]["new"] is None


# ── subject in serializer ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_incident_response_includes_subject_fields(client, acme_member, acme, phishing):
    incident = make_incident(acme, state="new", subject=phishing)
    client.force_login(acme_member)
    response = client.get(f"/api/incidents/{incident.display_id}/")
    data = response.json()
    assert data["subject"] == phishing.id
    assert data["subject_slug"] == "phishing"
    assert data["subject_name"] == "Phishing"


@pytest.mark.django_db
def test_incident_with_no_subject_returns_nulls(client, acme_member, acme):
    incident = make_incident(acme, state="new")
    client.force_login(acme_member)
    response = client.get(f"/api/incidents/{incident.display_id}/")
    data = response.json()
    assert data["subject"] is None
    assert data["subject_slug"] is None
    assert data["subject_name"] is None
