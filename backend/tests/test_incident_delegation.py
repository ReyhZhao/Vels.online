import pytest
from django.core.exceptions import ValidationError
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentDelegation, IncidentEvent
from incidents.services.delegation import delegate, return_delegation


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def assignee(db, django_user_model):
    return django_user_model.objects.create_user(username="assignee", password="pass", is_staff=True)


@pytest.fixture
def delegate_user(db, django_user_model):
    return django_user_model.objects.create_user(username="delegate", password="pass", is_staff=True)


@pytest.fixture
def other_staff(db, django_user_model):
    return django_user_model.objects.create_user(username="other_staff", password="pass", is_staff=True)


@pytest.fixture
def non_staff(db, django_user_model):
    return django_user_model.objects.create_user(username="regular", password="pass", is_staff=False)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="pass")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


def make_incident(org, assignee=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        assignee=assignee,
    )


# ── delegate service ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_delegate_creates_row(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee, note="please handle")
    assert d.id is not None
    assert d.user_id == delegate_user.id
    assert d.delegated_by_id == assignee.id
    assert d.note == "please handle"
    assert d.returned_at is None


@pytest.mark.django_db
def test_delegate_writes_event(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    delegate(incident, delegate_user, by=assignee, note="fyi")
    event = IncidentEvent.objects.get(incident=incident, kind="incident_delegated")
    assert event.payload["delegate_id"] == delegate_user.id
    assert event.payload["by_id"] == assignee.id
    assert event.payload["note"] == "fyi"


@pytest.mark.django_db
def test_delegate_rejects_non_staff(acme, assignee, non_staff):
    incident = make_incident(acme, assignee=assignee)
    with pytest.raises(ValidationError, match="staff"):
        delegate(incident, non_staff, by=assignee)


@pytest.mark.django_db
def test_delegate_rejects_self(acme, assignee):
    incident = make_incident(acme, assignee=assignee)
    with pytest.raises(ValidationError, match="assignee"):
        delegate(incident, assignee, by=assignee)


@pytest.mark.django_db
def test_multiple_active_delegations_allowed(acme, assignee, delegate_user, other_staff):
    incident = make_incident(acme, assignee=assignee)
    d1 = delegate(incident, delegate_user, by=assignee)
    d2 = delegate(incident, other_staff, by=assignee)
    active = IncidentDelegation.objects.filter(incident=incident, returned_at__isnull=True)
    assert active.count() == 2
    assert {d1.id, d2.id} == set(active.values_list("id", flat=True))


# ── return_delegation service ────────────────────────────────────────────────

@pytest.mark.django_db
def test_return_by_delegate(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    return_delegation(d, by=delegate_user)
    d.refresh_from_db()
    assert d.returned_at is not None
    assert d.returned_by_id == delegate_user.id


@pytest.mark.django_db
def test_return_by_assignee(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    return_delegation(d, by=assignee)
    d.refresh_from_db()
    assert d.returned_at is not None
    assert d.returned_by_id == assignee.id


@pytest.mark.django_db
def test_return_by_unrelated_user_rejected(acme, assignee, delegate_user, other_staff):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    with pytest.raises(ValidationError):
        return_delegation(d, by=other_staff)


@pytest.mark.django_db
def test_return_twice_raises_400(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    return_delegation(d, by=delegate_user)
    with pytest.raises(ValidationError, match="already been returned"):
        return_delegation(d, by=delegate_user)


@pytest.mark.django_db
def test_return_delegation_writes_event(acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    return_delegation(d, by=delegate_user)
    event = IncidentEvent.objects.filter(incident=incident, kind="incident_delegation_returned").first()
    assert event is not None
    assert event.payload["delegate_id"] == delegate_user.id
    assert event.payload["by_id"] == delegate_user.id


# ── endpoint: POST delegate ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_delegate_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.post(f"/api/incidents/{incident.id}/delegate/", {"user_id": 1}, content_type="application/json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_delegate_endpoint_requires_staff(client, acme, non_staff):
    incident = make_incident(acme)
    client.force_login(non_staff)
    response = client.post(f"/api/incidents/{incident.id}/delegate/", {"user_id": 1}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_delegate_endpoint_creates_delegation(client, acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    client.force_login(assignee)
    response = client.post(
        f"/api/incidents/{incident.id}/delegate/",
        {"user_id": delegate_user.id, "note": "please help"},
        content_type="application/json",
    )
    assert response.status_code == 201
    delegations = response.json()["active_delegations"]
    assert len(delegations) == 1
    assert delegations[0]["user"] == delegate_user.id


@pytest.mark.django_db
def test_delegate_endpoint_rejects_non_staff_delegate(client, acme, assignee, non_staff):
    incident = make_incident(acme, assignee=assignee)
    client.force_login(assignee)
    response = client.post(
        f"/api/incidents/{incident.id}/delegate/",
        {"user_id": non_staff.id},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_delegate_endpoint_returns_active_delegations_in_incident(client, acme, assignee, delegate_user, other_staff):
    incident = make_incident(acme, assignee=assignee)
    client.force_login(assignee)
    client.post(f"/api/incidents/{incident.id}/delegate/", {"user_id": delegate_user.id}, content_type="application/json")
    client.post(f"/api/incidents/{incident.id}/delegate/", {"user_id": other_staff.id}, content_type="application/json")
    response = client.get(f"/api/incidents/{incident.id}/")
    assert response.status_code == 200
    assert len(response.json()["active_delegations"]) == 2


# ── endpoint: POST return ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_return_endpoint_requires_auth(client, acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    response = client.post(f"/api/incidents/{incident.id}/delegations/{d.id}/return/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_return_endpoint_by_delegate(client, acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    client.force_login(delegate_user)
    response = client.post(f"/api/incidents/{incident.id}/delegations/{d.id}/return/")
    assert response.status_code == 200
    assert response.json()["active_delegations"] == []


@pytest.mark.django_db
def test_return_endpoint_by_assignee(client, acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    client.force_login(assignee)
    response = client.post(f"/api/incidents/{incident.id}/delegations/{d.id}/return/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_return_endpoint_by_unrelated_rejected(client, acme, assignee, delegate_user, other_staff):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    client.force_login(other_staff)
    response = client.post(f"/api/incidents/{incident.id}/delegations/{d.id}/return/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_return_endpoint_already_returned_gives_400(client, acme, assignee, delegate_user):
    incident = make_incident(acme, assignee=assignee)
    d = delegate(incident, delegate_user, by=assignee)
    return_delegation(d, by=delegate_user)
    client.force_login(assignee)
    response = client.post(f"/api/incidents/{incident.id}/delegations/{d.id}/return/")
    assert response.status_code == 400
