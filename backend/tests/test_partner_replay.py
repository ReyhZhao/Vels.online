"""Intake Inbox Replay (ADR-0035 / #714, #715): replay a held backlog through the live
partner pipeline, preview it first, and the staff endpoint surface."""

from unittest.mock import patch

import pytest

from incidents.models import Comment, Incident
from partners.models import Connection, ConnectionSender, IntakeInboxMessage
from partners.replay import replay_connection_backlog
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
def _verify_on(monkeypatch):
    # Replay re-runs the standard sender-auth gate; keep it ON so the raw must carry a
    # passing Authentication-Results header, exactly like live intake.
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "1")


class FakeStorage:
    """In-memory StorageClient stand-in keyed by object key."""

    def __init__(self, blobs=None):
        self.blobs = dict(blobs or {})
        self.deleted = []

    def get_bytes(self, key):
        return self.blobs[key]

    def delete_file(self, key):
        self.deleted.append(key)
        self.blobs.pop(key, None)

    def upload_file(self, file_obj, key):
        self.blobs[key] = file_obj.read()


def raw_eml(from_addr, subject, body="report body", auth_pass=True):
    headers = [f"From: {from_addr}", "To: soc@vels.online", f"Subject: {subject}"]
    if auth_pass:
        headers.append("Authentication-Results: mx.vels.online; dkim=pass; spf=pass")
    return ("\r\n".join(headers) + "\r\n\r\n" + body).encode()


def make_connection(acme, ref_regex=r"\[(CASE-\d+)\]", sender="peer@partner.example", active=True):
    conn = Connection.objects.create(
        name="Peer CSIRT", kind=Connection.KIND_CSIRT_PEER, organization=acme,
        external_reference_regex=ref_regex, active=active,
    )
    ConnectionSender.objects.create(connection=conn, address=sender)
    return conn


def make_row(sender, subject, key, storage, from_addr=None, **eml_kw):
    row = IntakeInboxMessage.objects.create(
        sender=sender, subject=subject, drop_reason="phishing:dropped:not_forward",
        raw_s3_key=key,
    )
    storage.blobs[key] = raw_eml(from_addr or sender, subject, **eml_kw)
    return row


# ── replay (slice 2 / #714) ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_backlog_creates_then_threads_oldest_first(acme):
    conn = make_connection(acme)
    storage = FakeStorage()
    r1 = make_row("peer@partner.example", "[CASE-7] initial report", "intake-inbox/1/raw.eml", storage)
    r2 = make_row("peer@partner.example", "[CASE-7] follow-up detail", "intake-inbox/2/raw.eml", storage)

    with patch("security.storage.StorageClient", return_value=storage):
        results = replay_connection_backlog(conn)

    # One incident created, the follow-up threaded onto it as an external comment.
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 1
    incident = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert Comment.objects.filter(incident=incident, origin=Comment.ORIGIN_PARTNER_INBOUND).count() == 1
    assert [x["outcome"] for x in results] == ["created", "matched"]

    r1.refresh_from_db(); r2.refresh_from_db()
    assert r1.replayed_incident_id == incident.id and r1.replayed_at is not None
    assert r2.replayed_incident_id == incident.id and r2.replayed_at is not None
    # Raw dropped on success (bytes now live as incident attachments).
    assert r1.raw_s3_key == "" and r2.raw_s3_key == ""
    assert set(storage.deleted) == {"intake-inbox/1/raw.eml", "intake-inbox/2/raw.eml"}


@pytest.mark.django_db
def test_reverification_failure_leaves_row_dead_lettered(acme):
    conn = make_connection(acme)
    storage = FakeStorage()
    row = make_row("peer@partner.example", "[CASE-9] report", "intake-inbox/1/raw.eml", storage, auth_pass=False)

    with patch("security.storage.StorageClient", return_value=storage):
        results = replay_connection_backlog(conn)

    assert results == [{"id": row.id, "outcome": "verification_failed"}]
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 0
    row.refresh_from_db()
    assert row.replayed_at is None
    assert row.raw_s3_key == "intake-inbox/1/raw.eml"  # unmarked, still replayable
    assert storage.deleted == []


@pytest.mark.django_db
def test_replay_is_idempotent(acme):
    conn = make_connection(acme)
    storage = FakeStorage()
    make_row("peer@partner.example", "[CASE-1] report", "intake-inbox/1/raw.eml", storage)

    with patch("security.storage.StorageClient", return_value=storage):
        first = replay_connection_backlog(conn)
        second = replay_connection_backlog(conn)

    assert len(first) == 1
    assert second == []  # already marked + raw dropped → nothing to do
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 1


@pytest.mark.django_db
def test_replay_ignores_uncovered_and_rawless_rows(acme):
    conn = make_connection(acme)
    storage = FakeStorage()
    covered = make_row("peer@partner.example", "[CASE-2] a", "intake-inbox/1/raw.eml", storage)
    # Different sender — not in this Connection's sender set.
    make_row("stranger@nowhere.example", "[CASE-3] b", "intake-inbox/2/raw.eml", storage)
    # Covered sender but no retained raw — cannot be replayed.
    IntakeInboxMessage.objects.create(sender="peer@partner.example", subject="[CASE-4] c", raw_s3_key="")

    with patch("security.storage.StorageClient", return_value=storage):
        results = replay_connection_backlog(conn)

    assert [x["id"] for x in results] == [covered.id]


# ── endpoint (slice 2 / #714) ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_replay_endpoint_requires_staff(client, regular_user, acme):
    conn = make_connection(acme)
    client.force_login(regular_user)
    assert client.post(f"/api/partners/connections/{conn.id}/replay-intake/").status_code == 403


@pytest.mark.django_db
def test_replay_endpoint_returns_outcomes(client, staff, acme):
    conn = make_connection(acme)
    storage = FakeStorage()
    make_row("peer@partner.example", "[CASE-5] report", "intake-inbox/1/raw.eml", storage)
    client.force_login(staff)
    with patch("security.storage.StorageClient", return_value=storage):
        res = client.post(f"/api/partners/connections/{conn.id}/replay-intake/")
    assert res.status_code == 200
    assert res.json()["results"][0]["outcome"] == "created"


# ── list surface (slice 2 / #714) ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_exposes_covering_connection_and_replayed_incident(client, staff, acme):
    conn = make_connection(acme)
    IntakeInboxMessage.objects.create(sender="peer@partner.example", subject="[CASE-6] x", raw_s3_key="intake-inbox/1/raw.eml")
    IntakeInboxMessage.objects.create(sender="stranger@nowhere.example", subject="y", raw_s3_key="intake-inbox/2/raw.eml")
    incident = Incident.objects.create(
        organization=acme, source_kind=Incident.SOURCE_PARTNER, display_id="INC-42",
        title="t", description="d", severity="medium", tlp="amber", pap="amber",
    )
    IntakeInboxMessage.objects.create(
        sender="peer@partner.example", subject="[CASE-6] done", replayed_incident=incident,
    )

    client.force_login(staff)
    rows = {r["subject"]: r for r in client.get("/api/partners/intake-inbox/").json()}

    covered = rows["[CASE-6] x"]
    assert covered["covering_connection"] == {"id": conn.id, "name": conn.name}
    assert covered["has_raw"] is True and covered["replayed_incident"] is None

    assert rows["y"]["covering_connection"] is None  # uncovered sender

    replayed = rows["[CASE-6] done"]
    assert replayed["replayed_incident"] == {"id": incident.id, "display_id": "INC-42"}
