"""Partner intake slice 5 (#673): bi-directional outbound sync (ADR-0033)."""

import pytest
from django.core import mail

from incidents.models import Comment, Incident, IncidentEvent
from incidents.services.transitions import transition_incident
from partners.models import Connection, ConnectionSender
from partners.sync import should_sync_to_partner, sync_comment_to_partner
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


def make_connection(org, direction=Connection.DIRECTION_BIDIRECTIONAL):
    conn = Connection.objects.create(name="Peer", kind=Connection.KIND_CSIRT_PEER, organization=org, direction=direction)
    ConnectionSender.objects.create(connection=conn, address="soc@peer.example")
    return conn


def partner_incident(org, connection, tlp="amber", ext_ref="INC-2024-0001"):
    return Incident.objects.create(
        organization=org, title="Peer case", display_id=f"INC-2026-{connection.id:04d}",
        source_kind=Incident.SOURCE_PARTNER, tlp=tlp,
        source_ref={"connection_id": connection.id, "external_reference": ext_ref, "sender_address": "soc@peer.example"},
    )


def mk_comment(incident, author=None, is_internal=False, kind=Comment.KIND_USER, origin=Comment.ORIGIN_STAFF, body="hello partner"):
    return Comment.objects.create(incident=incident, author=author, body=body, kind=kind, origin=origin, is_internal=is_internal)


# ── should_sync_to_partner gate matrix ───────────────────────────────────────────


@pytest.mark.django_db
def test_staff_external_on_bidirectional_non_red_syncs(acme, staff):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, author=staff)) is True


@pytest.mark.django_db
def test_inbound_only_connection_never_syncs(acme, staff):
    conn = make_connection(acme, direction=Connection.DIRECTION_INBOUND_ONLY)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, author=staff)) is False


@pytest.mark.django_db
def test_internal_comment_never_syncs(acme, staff):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, author=staff, is_internal=True)) is False


@pytest.mark.django_db
def test_partner_inbound_origin_never_syncs(acme):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, origin=Comment.ORIGIN_PARTNER_INBOUND)) is False


@pytest.mark.django_db
def test_ai_origin_never_syncs(acme):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, origin=Comment.ORIGIN_AI)) is False


@pytest.mark.django_db
def test_ai_kind_never_syncs(acme):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    assert should_sync_to_partner(mk_comment(inc, kind=Comment.KIND_AI_TRIAGE)) is False


@pytest.mark.django_db
def test_tlp_red_suppresses(acme, staff):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn, tlp="red")
    assert should_sync_to_partner(mk_comment(inc, author=staff)) is False


@pytest.mark.django_db
def test_non_partner_incident_never_syncs(acme, staff):
    inc = Incident.objects.create(organization=acme, title="normal", display_id="INC-2026-9999", tlp="amber")
    assert should_sync_to_partner(mk_comment(inc, author=staff)) is False


# ── send effects ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sync_comment_sends_email_and_records(acme, staff, settings):
    settings.DEFAULT_FROM_EMAIL = "soc@vels.online"
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    mail.outbox = []
    assert sync_comment_to_partner(mk_comment(inc, author=staff, body="please investigate")) is True
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["soc@peer.example"]
    assert "INC-2024-0001" in sent.subject  # External Reference carried in subject
    assert IncidentEvent.objects.filter(incident=inc, kind="partner_message_sent").exists()
    assert inc.comments.filter(metadata__partner_outbound=True).exists()


@pytest.mark.django_db
def test_closure_notifies_partner(acme, staff, settings):
    settings.DEFAULT_FROM_EMAIL = "soc@vels.online"
    conn = make_connection(acme)
    inc = partner_incident(acme, conn)
    inc.state = Incident.STATE_IN_PROGRESS
    inc.save(update_fields=["state"])
    mail.outbox = []
    transition_incident(inc, "closed", actor=staff, closure_reason=Incident.CLOSURE_NO_IMPACT)
    assert len(mail.outbox) == 1
    assert IncidentEvent.objects.filter(incident=inc, kind="partner_message_sent").exists()


@pytest.mark.django_db
def test_tlp_red_closure_does_not_notify(acme, staff):
    conn = make_connection(acme)
    inc = partner_incident(acme, conn, tlp="red")
    inc.state = Incident.STATE_IN_PROGRESS
    inc.save(update_fields=["state"])
    mail.outbox = []
    transition_incident(inc, "closed", actor=staff, closure_reason=Incident.CLOSURE_NO_IMPACT)
    assert len(mail.outbox) == 0
    assert not IncidentEvent.objects.filter(incident=inc, kind="partner_message_sent").exists()
