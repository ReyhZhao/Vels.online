"""Partner intake slice 1 (#669): Connection model + staff-only CRUD."""

import pytest

from partners.models import Connection, ConnectionSender
from security.models import Organization


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="user", password="pass")


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def connection(db, org, staff):
    conn = Connection.objects.create(name="Peer CSIRT", kind=Connection.KIND_CSIRT_PEER, organization=org, created_by=staff)
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    return conn


# ── permissions ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_staff(client, regular_user):
    client.force_login(regular_user)
    assert client.get("/api/partners/connections/").status_code == 403


@pytest.mark.django_db
def test_create_requires_staff(client, regular_user, org):
    client.force_login(regular_user)
    resp = client.post(
        "/api/partners/connections/",
        {"name": "X", "kind": "csirt_peer", "organization": org.id, "sender_addresses": ["a@b.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 403


# ── CRUD round-trip ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_and_list(client, staff, org):
    client.force_login(staff)
    resp = client.post(
        "/api/partners/connections/",
        {
            "name": "Peer",
            "kind": "csirt_peer",
            "organization": org.id,
            "direction": "bidirectional",
            "external_reference_regex": r"\[(INC-\d+)\]",
            "field_mappings": {"severity": {"regex": r"Sev:\s*(\w+)", "value_map": {"P1": "critical"}, "default": "medium"}},
            "sender_addresses": ["SOC@Peer.Example", "alerts@peer.example"],
        },
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    data = resp.json()
    # addresses normalised to lowercase and round-tripped as a flat list
    assert sorted(data["sender_addresses"]) == ["alerts@peer.example", "soc@peer.example"]
    assert data["organization_name"] == "Acme"
    assert data["created_by"] == staff.id

    listing = client.get("/api/partners/connections/").json()
    assert len(listing) == 1


@pytest.mark.django_db
def test_update_replaces_senders(client, staff, connection):
    client.force_login(staff)
    resp = client.patch(
        f"/api/partners/connections/{connection.id}/",
        {"name": "Renamed", "sender_addresses": ["new@peer.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    connection.refresh_from_db()
    assert connection.name == "Renamed"
    assert list(connection.senders.values_list("address", flat=True)) == ["new@peer.example"]


@pytest.mark.django_db
def test_delete_frees_the_sender_address(client, staff, connection, org):
    client.force_login(staff)
    assert client.delete(f"/api/partners/connections/{connection.id}/").status_code == 204
    assert not Connection.objects.filter(id=connection.id).exists()
    # the freed address can now be claimed by a new Connection
    resp = client.post(
        "/api/partners/connections/",
        {"name": "New", "kind": "csirt_peer", "organization": org.id, "sender_addresses": ["soc@peer.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 201


# ── sender uniqueness ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sender_uniqueness_across_connections(client, staff, connection, org):
    client.force_login(staff)
    resp = client.post(
        "/api/partners/connections/",
        {"name": "Other", "kind": "csirt_peer", "organization": org.id, "sender_addresses": ["SOC@peer.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "sender_addresses" in resp.json()


@pytest.mark.django_db
def test_duplicate_sender_within_one_connection_rejected(client, staff, org):
    client.force_login(staff)
    resp = client.post(
        "/api/partners/connections/",
        {"name": "Dup", "kind": "csirt_peer", "organization": org.id, "sender_addresses": ["a@b.example", "A@B.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_editing_a_connection_keeps_its_own_senders(client, staff, connection):
    """Re-saving a Connection with its existing sender must not trip the uniqueness check."""
    client.force_login(staff)
    resp = client.patch(
        f"/api/partners/connections/{connection.id}/",
        {"sender_addresses": ["soc@peer.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_invalid_regex_rejected(client, staff, org):
    client.force_login(staff)
    resp = client.post(
        "/api/partners/connections/",
        {"name": "Bad", "kind": "csirt_peer", "organization": org.id, "external_reference_regex": "[unclosed", "sender_addresses": ["a@b.example"]},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "external_reference_regex" in resp.json()
