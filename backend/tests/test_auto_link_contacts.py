import pytest
from contacts.models import AssetOwner, Contact, IncidentContact
from incidents.models import Asset, Incident, IncidentAsset
from security.models import Organization, OrganizationMembership


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


def make_incident(org, n=1):
    return Incident.objects.create(
        organization=org, title="Test", display_id=f"INC-2026-{n:04d}", tlp="amber"
    )


def make_contact(org, email="c@example.com"):
    return Contact.objects.create(organisation=org, name="Contact", email=email)


def make_asset(org, name="host-1"):
    return Asset.objects.create(organization=org, kind=Asset.KIND_HOST, name=name, agent_name=name)


# ── auto_link_contacts_for_asset ──────────────────────────────────────────────


@pytest.mark.django_db
def test_creates_incident_contact_for_asset_owner(acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    asset = make_asset(acme)
    AssetOwner.objects.create(contact=contact, asset=asset)

    from incidents.services.contacts import auto_link_contacts_for_asset
    auto_link_contacts_for_asset(incident, asset)

    assert IncidentContact.objects.filter(incident=incident, contact=contact, role=IncidentContact.ROLE_NOTIFIED).exists()


@pytest.mark.django_db
def test_idempotent_double_call(acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    asset = make_asset(acme)
    AssetOwner.objects.create(contact=contact, asset=asset)

    from incidents.services.contacts import auto_link_contacts_for_asset
    auto_link_contacts_for_asset(incident, asset)
    auto_link_contacts_for_asset(incident, asset)

    assert IncidentContact.objects.filter(incident=incident, contact=contact).count() == 1


@pytest.mark.django_db
def test_asset_with_no_owners_produces_no_links(acme):
    incident = make_incident(acme)
    asset = make_asset(acme)

    from incidents.services.contacts import auto_link_contacts_for_asset
    auto_link_contacts_for_asset(incident, asset)

    assert IncidentContact.objects.filter(incident=incident).count() == 0


@pytest.mark.django_db
def test_multiple_owners_all_linked(acme):
    incident = make_incident(acme)
    c1 = make_contact(acme, email="c1@acme.com")
    c2 = make_contact(acme, email="c2@acme.com")
    asset = make_asset(acme)
    AssetOwner.objects.create(contact=c1, asset=asset)
    AssetOwner.objects.create(contact=c2, asset=asset)

    from incidents.services.contacts import auto_link_contacts_for_asset
    auto_link_contacts_for_asset(incident, asset)

    assert IncidentContact.objects.filter(incident=incident).count() == 2


# ── wire-up: link_asset_from_source_ref ──────────────────────────────────────


@pytest.mark.django_db
def test_contacts_linked_via_source_ref_wire_up(acme):
    incident = make_incident(acme)
    asset = make_asset(acme, name="wazuh-host")
    contact = make_contact(acme)
    AssetOwner.objects.create(contact=contact, asset=asset)

    from incidents.services.assets import link_asset_from_source_ref
    link_asset_from_source_ref(incident, "wazuh_event", {"agent_name": "wazuh-host"})

    assert IncidentContact.objects.filter(incident=incident, contact=contact).exists()


# ── wire-up: manual asset-add API ────────────────────────────────────────────


@pytest.mark.django_db
def test_contacts_linked_via_manual_asset_add(client, acme_member, acme):
    incident = make_incident(acme)
    asset = make_asset(acme)
    contact = make_contact(acme)
    AssetOwner.objects.create(contact=contact, asset=asset)

    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{incident.display_id}/assets/",
        {"asset": asset.id},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert IncidentContact.objects.filter(incident=incident, contact=contact).exists()


# ── GET /api/incidents/<display_id>/contacts/ ─────────────────────────────────


@pytest.mark.django_db
def test_get_contacts_requires_auth(client, acme):
    incident = make_incident(acme)
    assert client.get(f"/api/incidents/{incident.display_id}/contacts/").status_code == 401


@pytest.mark.django_db
def test_get_contacts_returns_linked_contacts(client, acme_member, acme):
    incident = make_incident(acme)
    contact = make_contact(acme)
    IncidentContact.objects.create(incident=incident, contact=contact, role=IncidentContact.ROLE_NOTIFIED)
    client.force_login(acme_member)
    data = client.get(f"/api/incidents/{incident.display_id}/contacts/").json()
    assert len(data) == 1
    assert data[0]["name"] == "Contact"
    assert data[0]["role"] == "notified"


@pytest.mark.django_db
def test_get_contacts_empty_for_incident_with_no_contacts(client, acme_member, acme):
    incident = make_incident(acme)
    client.force_login(acme_member)
    data = client.get(f"/api/incidents/{incident.display_id}/contacts/").json()
    assert data == []
