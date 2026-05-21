import pytest
from contacts.models import Contact, IncidentContact
from incidents.models import Incident
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


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


def make_incident(org, n=1):
    return Incident.objects.create(
        organization=org, title="Test", display_id=f"INC-2026-{n:04d}", tlp="amber"
    )


def make_contact(org, email="c@example.com"):
    return Contact.objects.create(organisation=org, name="Carol", email=email)


# ── POST /api/incidents/<display_id>/contacts/ ────────────────────────────────


@pytest.mark.django_db
def test_link_contact_requires_auth(client, acme):
    inc = make_incident(acme)
    resp = client.post(f"/api/incidents/{inc.display_id}/contacts/", {}, content_type="application/json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_link_contact_creates_row(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contacts/",
        {"contact_id": c.id, "role": "questioned", "message": "Did you see this?"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "questioned"
    assert data["message"] == "Did you see this?"
    assert IncidentContact.objects.filter(incident=inc, contact=c).exists()


@pytest.mark.django_db
def test_link_contact_from_different_org_rejected(client, acme_member, acme, contoso):
    inc = make_incident(acme)
    other = make_contact(contoso, email="other@contoso.com")
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contacts/",
        {"contact_id": other.id, "role": "notified"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_link_duplicate_contact_rejected(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=c)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contacts/",
        {"contact_id": c.id, "role": "notified"},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── PATCH /api/incidents/<display_id>/contacts/<id>/ ─────────────────────────


@pytest.mark.django_db
def test_patch_updates_role_and_message(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    row = IncidentContact.objects.create(incident=inc, contact=c, role="notified")
    client.force_login(acme_member)
    resp = client.patch(
        f"/api/incidents/{inc.display_id}/contacts/{row.id}/",
        {"role": "questioned", "message": "Updated"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "questioned"
    assert data["message"] == "Updated"


@pytest.mark.django_db
def test_patch_updates_role_only(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    row = IncidentContact.objects.create(incident=inc, contact=c, role="notified", message="original")
    client.force_login(acme_member)
    resp = client.patch(
        f"/api/incidents/{inc.display_id}/contacts/{row.id}/",
        {"role": "questioned"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "questioned"
    assert data["message"] == "original"


# ── DELETE /api/incidents/<display_id>/contacts/<id>/ ────────────────────────


@pytest.mark.django_db
def test_delete_removes_link(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    row = IncidentContact.objects.create(incident=inc, contact=c)
    client.force_login(acme_member)
    resp = client.delete(f"/api/incidents/{inc.display_id}/contacts/{row.id}/")
    assert resp.status_code == 204
    assert not IncidentContact.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_delete_wrong_incident_returns_404(client, acme_member, acme):
    inc1 = make_incident(acme, n=1)
    inc2 = make_incident(acme, n=2)
    c = make_contact(acme)
    row = IncidentContact.objects.create(incident=inc1, contact=c)
    client.force_login(acme_member)
    resp = client.delete(f"/api/incidents/{inc2.display_id}/contacts/{row.id}/")
    assert resp.status_code == 404


# ── org isolation ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cannot_get_contacts_for_other_org_incident(client, alice, contoso):
    inc = make_incident(contoso)
    client.force_login(alice)
    resp = client.get(f"/api/incidents/{inc.display_id}/contacts/")
    assert resp.status_code == 404
