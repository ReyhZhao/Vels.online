"""Partner intake slice 4 (#672): inbound matching threads follow-ups by External Reference."""

from unittest.mock import MagicMock, patch

import pytest

from incidents.models import Comment, Incident, IncidentEvent
from inbound_mail.dataclasses import NormalisedMessage
from inbound_mail.router import route_inbound_message
from partners.matching import find_partner_incident
from partners.models import Connection, ConnectionSender
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "0")


@pytest.fixture(autouse=True)
def _mock_storage():
    with patch("security.storage.StorageClient", return_value=MagicMock()):
        yield


def csirt(org, **over):
    conn = Connection.objects.create(
        name="Peer", kind=Connection.KIND_CSIRT_PEER, organization=org,
        external_reference_regex=r"\[(INC-[\d-]+)\]", **over,
    )
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    return conn


def msg(subject, from_address="soc@peer.example", body="update text"):
    return NormalisedMessage(
        from_address=from_address, to_address="soc@vels.online", reply_to=None,
        subject=subject, body_text=body, body_html="", raw_bytes=b"raw",
    )


# ── find_partner_incident ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_find_matches_open_incident_by_reference(acme):
    conn = csirt(acme)
    route_inbound_message(msg("Detection [INC-2024-0001]"))
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert find_partner_incident(conn, "INC-2024-0001") == inc


@pytest.mark.django_db
def test_empty_reference_never_matches(acme):
    conn = csirt(acme)
    assert find_partner_incident(conn, "") is None


@pytest.mark.django_db
def test_closed_incident_is_not_matched(acme):
    conn = csirt(acme)
    route_inbound_message(msg("Detection [INC-2024-0002]"))
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    inc.state = Incident.STATE_CLOSED
    inc.save(update_fields=["state"])
    assert find_partner_incident(conn, "INC-2024-0002") is None


# ── handler threading ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_followup_appends_comment_not_duplicate_incident(acme):
    csirt(acme)
    assert route_inbound_message(msg("Detection [INC-2024-0010]")) == "partner:created"
    assert route_inbound_message(msg("Re: Detection [INC-2024-0010]", body="more info")) == "partner:matched"

    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 1
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    comment = inc.comments.get(origin=Comment.ORIGIN_PARTNER_INBOUND)
    assert comment.is_internal is False
    assert comment.author_id is None
    assert comment.metadata["partner_sender"] == "soc@peer.example"
    assert "more info" in comment.body
    assert IncidentEvent.objects.filter(incident=inc, kind="partner_message_received").count() == 2


@pytest.mark.django_db
def test_no_reference_creates_flagged_incident(acme):
    csirt(acme)
    assert route_inbound_message(msg("No reference here")) == "partner:created"
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert inc.source_ref.get("flagged_no_reference") is True


@pytest.mark.django_db
def test_unknown_reference_creates_new_incident(acme):
    csirt(acme)
    route_inbound_message(msg("Detection [INC-2024-0020]"))
    route_inbound_message(msg("Detection [INC-2024-0099]"))
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 2


@pytest.mark.django_db
def test_vendor_resend_of_same_advisory_dedups(acme):
    infra = Organization.get_infrastructure()
    conn = Connection.objects.create(
        name="Fortinet", kind=Connection.KIND_VENDOR, organization=infra,
        direction=Connection.DIRECTION_INBOUND_ONLY, external_reference_regex=r"(FG-IR-\d+-\d+)",
    )
    ConnectionSender.objects.create(connection=conn, address="psirt@fortinet.example")
    m1 = msg("Advisory FG-IR-24-001", from_address="psirt@fortinet.example")
    m2 = msg("Advisory FG-IR-24-001 (resend)", from_address="psirt@fortinet.example")
    assert route_inbound_message(m1) == "partner:created"
    assert route_inbound_message(m2) == "partner:matched"
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).count() == 1


@pytest.mark.django_db
def test_inbound_followup_never_changes_state(acme):
    csirt(acme)
    route_inbound_message(msg("Detection [INC-2024-0030]"))
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    inc.state = Incident.STATE_IN_PROGRESS
    inc.save(update_fields=["state"])
    route_inbound_message(msg("We are closing our side [INC-2024-0030]", body="closing"))
    inc.refresh_from_db()
    assert inc.state == Incident.STATE_IN_PROGRESS
