import pytest
from django.core.exceptions import ValidationError
from security.models import Organization
from alerts.models import Alert
from incidents.models import Asset, Incident, IncidentAsset, IncidentEvent
from incidents.services.change_org import change_incident_org


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def staff_actor(db, django_user_model):
    return django_user_model.objects.create_user(username="actor", password="pass", is_staff=True)


@pytest.fixture
def non_staff(db, django_user_model):
    return django_user_model.objects.create_user(username="regular", password="pass", is_staff=False)


def make_incident(org, state="triaged"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
    )


def make_alert(org, incident=None):
    count = Alert.objects.count()
    return Alert.objects.create(
        organization=org,
        display_id=f"AL-{count + 1:04d}",
        source_kind="wazuh_event",
        source_ref={"rule_id": "100002", "agent_name": "web-01"},
        severity="medium",
        state="new",
        incident=incident,
    )


# ── service unit tests ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_change_org_moves_incident_alerts_and_unlinks_assets(acme, contoso, staff_actor):
    incident = make_incident(acme)
    a1 = make_alert(acme, incident=incident)
    a2 = make_alert(acme, incident=incident)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    IncidentAsset.objects.create(incident=incident, asset=asset)

    change_incident_org(incident, contoso, actor=staff_actor)

    incident.refresh_from_db()
    a1.refresh_from_db()
    a2.refresh_from_db()
    assert incident.organization_id == contoso.id
    assert a1.organization_id == contoso.id
    assert a2.organization_id == contoso.id
    # Asset links removed, but the underlying Asset row still exists in its original org.
    assert incident.incident_assets.count() == 0
    asset.refresh_from_db()
    assert asset.organization_id == acme.id


@pytest.mark.django_db
def test_change_org_records_event_with_counts(acme, contoso, staff_actor):
    incident = make_incident(acme)
    make_alert(acme, incident=incident)
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01")
    IncidentAsset.objects.create(incident=incident, asset=asset)

    change_incident_org(incident, contoso, actor=staff_actor)

    event = IncidentEvent.objects.get(incident=incident, kind="incident_org_changed")
    assert event.payload["from"] == "acme"
    assert event.payload["to"] == "contoso"
    assert event.payload["alerts_relinked"] == 1
    assert event.payload["assets_unlinked"] == 1
    assert event.actor_id == staff_actor.id


@pytest.mark.django_db
def test_change_org_rejects_non_triage_state(acme, contoso, staff_actor):
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError):
        change_incident_org(incident, contoso, actor=staff_actor)
    incident.refresh_from_db()
    assert incident.organization_id == acme.id


@pytest.mark.django_db
def test_change_org_rejects_same_org(acme, staff_actor):
    incident = make_incident(acme)
    with pytest.raises(ValidationError):
        change_incident_org(incident, acme, actor=staff_actor)


@pytest.mark.django_db
def test_change_org_allowed_in_new_state(acme, contoso, staff_actor):
    incident = make_incident(acme, state="new")
    change_incident_org(incident, contoso, actor=staff_actor)
    incident.refresh_from_db()
    assert incident.organization_id == contoso.id


# ── endpoint tests ───────────────────────────────────────────────────────────

def _url(incident):
    return f"/api/incidents/{incident.display_id}/change-org/"


@pytest.mark.django_db
def test_change_org_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.post(_url(incident), {"organization": "contoso"}, content_type="application/json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_change_org_endpoint_requires_staff(client, acme, contoso, non_staff):
    incident = make_incident(acme)
    client.force_login(non_staff)
    response = client.post(_url(incident), {"organization": "contoso"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_change_org_endpoint_happy_path(client, acme, contoso, staff_actor):
    incident = make_incident(acme)
    make_alert(acme, incident=incident)
    client.force_login(staff_actor)
    response = client.post(_url(incident), {"organization": "contoso"}, content_type="application/json")
    assert response.status_code == 200
    assert response.json()["org_slug"] == "contoso"


@pytest.mark.django_db
def test_change_org_endpoint_rejects_wrong_state(client, acme, contoso, staff_actor):
    incident = make_incident(acme, state="resolved")
    client.force_login(staff_actor)
    response = client.post(_url(incident), {"organization": "contoso"}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_change_org_endpoint_rejects_same_org(client, acme, staff_actor):
    incident = make_incident(acme)
    client.force_login(staff_actor)
    response = client.post(_url(incident), {"organization": "acme"}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_change_org_endpoint_unknown_org_returns_404(client, acme, staff_actor):
    incident = make_incident(acme)
    client.force_login(staff_actor)
    response = client.post(_url(incident), {"organization": "nope"}, content_type="application/json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_change_org_endpoint_missing_incident_returns_404(client, contoso, staff_actor):
    client.force_login(staff_actor)
    response = client.post(
        "/api/incidents/INC-DOES-NOT-EXIST/change-org/",
        {"organization": "contoso"},
        content_type="application/json",
    )
    assert response.status_code == 404
