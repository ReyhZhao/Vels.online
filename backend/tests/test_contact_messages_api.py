import pytest
from unittest.mock import patch

from contacts.models import Contact, ContactMessage, IncidentContact
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


# ── POST /api/incidents/<display_id>/contact-messages/ ────────────────────────


@pytest.mark.django_db
def test_post_creates_outbound_message_and_sends_email(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)

    with patch("contacts.services.send_html_email") as mock_send:
        resp = client.post(
            f"/api/incidents/{inc.display_id}/contact-messages/",
            {"contact_id": c.id, "role": "notified", "body": "We are investigating."},
            content_type="application/json",
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["direction"] == "outbound"
    assert data["role"] == "notified"
    assert data["body"] == "We are investigating."
    assert ContactMessage.objects.filter(incident=inc, contact=c, direction="outbound").exists()
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_post_questioned_role_passes_reply_to(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)

    with patch("contacts.services.send_html_email") as mock_send:
        resp = client.post(
            f"/api/incidents/{inc.display_id}/contact-messages/",
            {"contact_id": c.id, "role": "questioned", "body": "Did you do this?"},
            content_type="application/json",
        )

    assert resp.status_code == 201
    _, kwargs = mock_send.call_args
    assert "reply_to" in kwargs
    assert len(kwargs["reply_to"]) == 1
    assert "@" in kwargs["reply_to"][0]


@pytest.mark.django_db
def test_post_notified_role_passes_no_reply_to(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)

    with patch("contacts.services.send_html_email") as mock_send:
        resp = client.post(
            f"/api/incidents/{inc.display_id}/contact-messages/",
            {"contact_id": c.id, "role": "notified", "body": "FYI."},
            content_type="application/json",
        )

    assert resp.status_code == 201
    _, kwargs = mock_send.call_args
    assert "reply_to" not in kwargs


@pytest.mark.django_db
def test_post_requires_auth(client, acme):
    inc = make_incident(acme)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/",
        {"contact_id": 1, "role": "notified", "body": "x"},
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_post_invalid_role_rejected(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/",
        {"contact_id": c.id, "role": "unknown", "body": "x"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_post_empty_body_rejected(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/",
        {"contact_id": c.id, "role": "notified", "body": "  "},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── GET /api/incidents/<display_id>/contact-messages/ ─────────────────────────


@pytest.mark.django_db
def test_get_returns_messages_grouped_by_contact(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=c)
    outbound = ContactMessage.objects.create(
        incident=inc, contact=c, direction="outbound", role="notified", body="Hey"
    )
    ContactMessage.objects.create(
        incident=inc, contact=c, direction="inbound", body="OK", parent=outbound
    )
    client.force_login(acme_member)

    resp = client.get(f"/api/incidents/{inc.display_id}/contact-messages/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    group = data[0]
    assert group["contact_id"] == c.id
    assert group["name"] == "Carol"
    assert len(group["messages"]) == 2


@pytest.mark.django_db
def test_get_includes_linked_contacts_with_no_messages(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    IncidentContact.objects.create(incident=inc, contact=c)
    client.force_login(acme_member)

    resp = client.get(f"/api/incidents/{inc.display_id}/contact-messages/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["messages"] == []


# ── POST /api/incidents/<display_id>/contact-messages/mark-read/ ──────────────


@pytest.mark.django_db
def test_mark_read_sets_read_at_on_unread_inbound(client, acme_member, acme):
    inc = make_incident(acme)
    c = make_contact(acme)
    msg = ContactMessage.objects.create(
        incident=inc, contact=c, direction="inbound", body="Hello"
    )
    assert msg.read_at is None
    client.force_login(acme_member)

    resp = client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/mark-read/",
        {"contact_id": c.id},
        content_type="application/json",
    )

    assert resp.status_code == 200
    msg.refresh_from_db()
    assert msg.read_at is not None


@pytest.mark.django_db
def test_mark_read_does_not_overwrite_already_read(client, acme_member, acme):
    from django.utils import timezone

    inc = make_incident(acme)
    c = make_contact(acme)
    original_time = timezone.now()
    msg = ContactMessage.objects.create(
        incident=inc, contact=c, direction="inbound", body="Hello", read_at=original_time
    )
    client.force_login(acme_member)

    client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/mark-read/",
        {"contact_id": c.id},
        content_type="application/json",
    )

    msg.refresh_from_db()
    assert msg.read_at == original_time


@pytest.mark.django_db
def test_mark_read_only_affects_given_contact(client, acme_member, acme):
    inc = make_incident(acme)
    c1 = make_contact(acme, email="c1@example.com")
    c2 = make_contact(acme, email="c2@example.com")
    msg1 = ContactMessage.objects.create(incident=inc, contact=c1, direction="inbound", body="From c1")
    msg2 = ContactMessage.objects.create(incident=inc, contact=c2, direction="inbound", body="From c2")
    client.force_login(acme_member)

    client.post(
        f"/api/incidents/{inc.display_id}/contact-messages/mark-read/",
        {"contact_id": c1.id},
        content_type="application/json",
    )

    msg1.refresh_from_db()
    msg2.refresh_from_db()
    assert msg1.read_at is not None
    assert msg2.read_at is None


# ── Org isolation ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cannot_post_contact_message_on_other_org_incident(client, alice, contoso, acme):
    inc = make_incident(contoso)
    OrganizationMembership.objects.create(user=alice, organization=acme)
    client.force_login(alice)

    with patch("contacts.services.send_html_email"):
        resp = client.post(
            f"/api/incidents/{inc.display_id}/contact-messages/",
            {"contact_id": 1, "role": "notified", "body": "x"},
            content_type="application/json",
        )

    assert resp.status_code == 404


@pytest.mark.django_db
def test_cannot_get_contact_messages_on_other_org_incident(client, alice, contoso):
    inc = make_incident(contoso)
    client.force_login(alice)

    resp = client.get(f"/api/incidents/{inc.display_id}/contact-messages/")

    assert resp.status_code == 404
