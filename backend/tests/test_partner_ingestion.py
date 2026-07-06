"""Partner intake slice 2 (#670): PartnerIngestionHandler + router integration."""

from unittest.mock import MagicMock, patch

import pytest

from incidents.models import Incident, IncidentEvent
from inbound_mail.dataclasses import NormalisedAttachment, NormalisedMessage
from inbound_mail.router import route_inbound_message
from partners.models import Connection, ConnectionSender
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture(autouse=True)
def _soc_mailbox(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    # These tests exercise ingestion/mapping, not the DKIM/SPF gate (slice 3) — turn it
    # off so raw_bytes without Authentication-Results still ingest.
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "0")


@pytest.fixture(autouse=True)
def _mock_storage():
    with patch("security.storage.StorageClient", return_value=MagicMock()) as m:
        yield m


def csirt_connection(org, **over):
    conn = Connection.objects.create(
        name="Peer CSIRT",
        kind=Connection.KIND_CSIRT_PEER,
        organization=org,
        external_reference_regex=r"\[(INC-[\d-]+)\]",
        field_mappings={"severity": {"regex": r"Severity:\s*(\w+)", "value_map": {"P1": "critical"}, "default": "medium"}},
        **over,
    )
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    return conn


def partner_message(subject="Detected malware [INC-2024-0142]", from_address="soc@peer.example", body="Severity: P1"):
    return NormalisedMessage(
        from_address=from_address, to_address="soc@vels.online", reply_to=None,
        subject=subject, body_text=body, body_html="", raw_bytes=b"raw eml bytes",
    )


@pytest.mark.django_db
def test_connection_sender_email_creates_partner_incident(acme):
    csirt_connection(acme)
    outcome = route_inbound_message(partner_message())
    assert outcome == "partner:created"

    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert inc.organization == acme
    assert inc.severity == "critical"  # P1 → critical via value_map
    assert inc.source_ref["external_reference"] == "INC-2024-0142"
    assert inc.source_ref["sender_address"] == "soc@peer.example"
    assert "connection_id" in inc.source_ref
    assert IncidentEvent.objects.filter(incident=inc, kind="partner_message_received").exists()
    assert inc.attachments.filter(content_type="message/rfc822").exists()


@pytest.mark.django_db
def test_display_name_from_address_still_matches(acme):
    csirt_connection(acme)
    outcome = route_inbound_message(partner_message(from_address="Peer SOC <SOC@Peer.Example>"))
    assert outcome == "partner:created"


@pytest.mark.django_db
def test_vendor_connection_uses_infrastructure_org_and_advisory_subject():
    infra = Organization.get_infrastructure()
    conn = Connection.objects.create(name="Fortinet", kind=Connection.KIND_VENDOR, organization=infra, direction=Connection.DIRECTION_INBOUND_ONLY)
    ConnectionSender.objects.create(connection=conn, address="psirt@fortinet.example")
    msg = partner_message(subject="FG-IR-24-001 advisory", from_address="psirt@fortinet.example", body="patch available")
    route_inbound_message(msg)
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert inc.organization == infra
    assert inc.subject is not None and inc.subject.name == "Vendor Advisory"


@pytest.mark.django_db
def test_file_attachments_passed_through(acme):
    csirt_connection(acme)
    msg = partner_message()
    msg.attachments = [NormalisedAttachment(filename="ioc.csv", content_type="text/csv", payload=b"1.2.3.4")]
    route_inbound_message(msg)
    inc = Incident.objects.get(source_kind=Incident.SOURCE_PARTNER)
    assert inc.attachments.filter(filename="ioc.csv").exists()


@pytest.mark.django_db
def test_inactive_connection_does_not_ingest(acme):
    csirt_connection(acme, active=False)
    outcome = route_inbound_message(partner_message())
    # Falls through to the phishing handler (to == soc@) which drops a non-forward.
    assert outcome != "partner:created"
    assert not Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).exists()


@pytest.mark.django_db
def test_unknown_sender_is_not_claimed_by_partner_handler(acme):
    csirt_connection(acme)
    outcome = route_inbound_message(partner_message(from_address="stranger@nowhere.example"))
    assert outcome != "partner:created"
    assert not Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).exists()
