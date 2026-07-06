"""Partner intake slice 3 (#671): DKIM/SPF sender-auth verification gate."""

from unittest.mock import MagicMock, patch

import pytest

from incidents.models import Incident
from inbound_mail.dataclasses import NormalisedMessage
from inbound_mail.router import route_inbound_message
from partners.models import Connection, ConnectionSender
from partners.verification import verify_message_auth
from security.models import Organization


def raw_with_auth(dkim="pass", spf="pass"):
    return (
        f"Authentication-Results: mx.vels.online; dkim={dkim} header.d=peer.example; spf={spf} smtp.mailfrom=peer.example\r\n"
        "From: soc@peer.example\r\nSubject: test\r\n\r\nbody"
    ).encode()


# ── pure verify_message_auth ─────────────────────────────────────────────────────


def test_dkim_and_spf_pass_verifies():
    assert verify_message_auth(raw_with_auth("pass", "pass")) is True


def test_dkim_fail_rejected():
    assert verify_message_auth(raw_with_auth("fail", "pass")) is False


def test_spf_fail_rejected():
    assert verify_message_auth(raw_with_auth("pass", "fail")) is False


def test_missing_header_rejected():
    assert verify_message_auth(b"From: x@y.example\r\nSubject: t\r\n\r\nbody") is False


def test_empty_message_rejected():
    assert verify_message_auth(b"") is False


def test_env_gate_off_always_passes(monkeypatch):
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "0")
    assert verify_message_auth(b"") is True
    assert verify_message_auth(raw_with_auth("fail", "fail")) is True


def test_default_is_on(monkeypatch):
    monkeypatch.delenv("PARTNER_INTAKE_VERIFY_AUTH", raising=False)
    assert verify_message_auth(b"") is False


# ── handler gate integration ─────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("INBOUND_IMAP_USER", "soc@vels.online")
    monkeypatch.setenv("PARTNER_INTAKE_VERIFY_AUTH", "1")  # gate ON


@pytest.fixture(autouse=True)
def _mock_storage():
    with patch("security.storage.StorageClient", return_value=MagicMock()):
        yield


def connection(org):
    conn = Connection.objects.create(name="Peer", kind=Connection.KIND_CSIRT_PEER, organization=org)
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    return conn


def message(raw_bytes):
    return NormalisedMessage(
        from_address="soc@peer.example", to_address="soc@vels.online", reply_to=None,
        subject="Peer detection", body_text="details", body_html="", raw_bytes=raw_bytes,
    )


@pytest.mark.django_db
def test_failed_verification_drops_and_creates_no_incident(acme):
    connection(acme)
    outcome = route_inbound_message(message(raw_with_auth("fail", "pass")))
    assert outcome == "partner:dropped:verification_failed"
    assert not Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).exists()


@pytest.mark.django_db
def test_verified_sender_still_ingests(acme):
    connection(acme)
    outcome = route_inbound_message(message(raw_with_auth("pass", "pass")))
    assert outcome == "partner:created"
    assert Incident.objects.filter(source_kind=Incident.SOURCE_PARTNER).exists()
