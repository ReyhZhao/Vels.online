"""Partner intake slice 7 (#675): Intake Inbox capture, purge, and staff API."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from inbound_mail.dataclasses import NormalisedMessage
from inbound_mail.router import route_inbound_message
from partners.models import Connection, ConnectionSender, IntakeInboxMessage
from partners.tasks import purge_intake_inbox
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="u", password="p")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")


def message(from_address="stranger@nowhere.example", to_address="soc@vels.online", subject="hi", body="body text"):
    return NormalisedMessage(
        from_address=from_address, to_address=to_address, reply_to=None,
        subject=subject, body_text=body, body_html="", raw_bytes=b"raw",
    )


# ── capture ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unrecognised_to_lands_in_inbox(acme):
    outcome = route_inbound_message(message(to_address="someone@else.example"))
    assert outcome == "dropped:unrecognised_to"
    row = IntakeInboxMessage.objects.get()
    assert row.sender == "stranger@nowhere.example"
    assert row.drop_reason == "dropped:unrecognised_to"
    assert row.body_excerpt == "body text"


@pytest.mark.django_db
def test_phishing_drop_lands_in_inbox(acme):
    # A non-forwarded email to the SOC mailbox is dropped by the phishing handler.
    outcome = route_inbound_message(message(subject="not a forward"))
    assert outcome.startswith("phishing:dropped:")
    assert IntakeInboxMessage.objects.filter(drop_reason=outcome).exists()


@pytest.mark.django_db
def test_verification_failure_lands_in_inbox(acme, monkeypatch):
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "1")
    conn = Connection.objects.create(name="Peer", kind=Connection.KIND_CSIRT_PEER, organization=acme)
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    with patch("security.storage.StorageClient", return_value=MagicMock()):
        outcome = route_inbound_message(message(from_address="soc@peer.example"))  # no auth headers
    assert outcome == "partner:dropped:verification_failed"
    assert IntakeInboxMessage.objects.filter(drop_reason=outcome, sender="soc@peer.example").exists()


@pytest.mark.django_db
def test_successful_partner_ingest_does_not_land_in_inbox(acme, monkeypatch):
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "0")
    conn = Connection.objects.create(name="Peer", kind=Connection.KIND_CSIRT_PEER, organization=acme)
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    with patch("security.storage.StorageClient", return_value=MagicMock()):
        outcome = route_inbound_message(message(from_address="soc@peer.example"))
    assert outcome == "partner:created"
    assert IntakeInboxMessage.objects.count() == 0


# ── purge ────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_purge_removes_aged_rows(monkeypatch):
    monkeypatch.setenv("PARTNER_INTAKE_RETENTION_DAYS", "30")
    fresh = IntakeInboxMessage.objects.create(sender="a@x.example", drop_reason="dropped:x")
    old = IntakeInboxMessage.objects.create(sender="b@x.example", drop_reason="dropped:x")
    # auto_now_add can't be set at create; backdate directly.
    IntakeInboxMessage.objects.filter(pk=old.pk).update(received_at=timezone.now() - timedelta(days=40))

    deleted = purge_intake_inbox()
    assert deleted == 1
    assert IntakeInboxMessage.objects.filter(pk=fresh.pk).exists()
    assert not IntakeInboxMessage.objects.filter(pk=old.pk).exists()


# ── API ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_staff(client, regular_user):
    client.force_login(regular_user)
    assert client.get("/api/partners/intake-inbox/").status_code == 403


@pytest.mark.django_db
def test_staff_lists_and_dismisses(client, staff):
    row = IntakeInboxMessage.objects.create(sender="a@x.example", subject="s", drop_reason="dropped:x")
    client.force_login(staff)
    listing = client.get("/api/partners/intake-inbox/")
    assert listing.status_code == 200
    assert listing.json()[0]["sender"] == "a@x.example"
    assert client.delete(f"/api/partners/intake-inbox/{row.id}/").status_code == 204
    assert not IntakeInboxMessage.objects.filter(pk=row.id).exists()


@pytest.mark.django_db
def test_count_requires_staff(client, regular_user):
    client.force_login(regular_user)
    assert client.get("/api/partners/intake-inbox/count/").status_code == 403


@pytest.mark.django_db
def test_count_returns_inbox_total(client, staff):
    IntakeInboxMessage.objects.create(sender="a@x.example", drop_reason="dropped:x")
    IntakeInboxMessage.objects.create(sender="b@x.example", drop_reason="dropped:y")
    client.force_login(staff)
    res = client.get("/api/partners/intake-inbox/count/")
    assert res.status_code == 200
    assert res.json() == {"count": 2}
