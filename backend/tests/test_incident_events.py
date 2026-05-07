import pytest
from security.models import Organization
from incidents.models import Incident, IncidentEvent
from incidents.services.events import record_event


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(acme):
    return Incident.objects.create(organization=acme, title="Test", display_id="INC-2026-0001")


@pytest.mark.django_db
def test_record_event_creates_row(incident):
    record_event(incident, "incident_created")
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_created").count() == 1


@pytest.mark.django_db
def test_record_event_stores_payload(incident):
    record_event(incident, "incident_updated", payload={"changes": {"title": {"old": "A", "new": "B"}}})
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["title"]["new"] == "B"


@pytest.mark.django_db
def test_record_event_stores_actor(incident, django_user_model):
    user = django_user_model.objects.create_user(username="actor", password="pass")
    record_event(incident, "incident_created", actor=user)
    event = IncidentEvent.objects.get(incident=incident)
    assert event.actor == user
