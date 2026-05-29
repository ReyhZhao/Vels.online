"""Tests for #319: email IOC extraction for phishing incidents."""
import pytest

from incidents.models import IOC, Incident
from incidents.services.ioc_extraction import extract_and_save_iocs
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def _phishing_incident(acme, sender="phisher@evil.com", forwarder="user@corp.com", subject="win a prize"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        display_id=f"INC-2026-P{count + 1:04d}",
        title=f"Phishing: {subject}",
        description=f"Forwarded phishing email from {sender}.",
        source_kind="inbound_email",
        source_ref={
            "sender_address": sender,
            "subject_normalised": subject,
            "forwarder_address": forwarder,
        },
    )


@pytest.mark.django_db
def test_extracts_sender_as_email_ioc(acme):
    incident = _phishing_incident(acme, sender="phisher@evil.com")
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL, value="phisher@evil.com").exists()


@pytest.mark.django_db
def test_forwarder_excluded(acme):
    incident = _phishing_incident(acme, sender="phisher@evil.com", forwarder="user@corp.com")
    extract_and_save_iocs(incident)
    assert not IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL, value="user@corp.com").exists()


@pytest.mark.django_db
def test_soc_address_excluded(acme):
    incident = Incident.objects.create(
        organization=acme,
        display_id="INC-2026-SOC",
        title="Phishing: win",
        description="forwarded by soc@vels.online",
        source_kind="inbound_email",
        source_ref={
            "sender_address": "phisher@evil.com",
            "subject_normalised": "win",
            "forwarder_address": "user@corp.com",
        },
    )
    extract_and_save_iocs(incident)
    assert not IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL, value="soc@vels.online").exists()


@pytest.mark.django_db
def test_email_ioc_from_description_text(acme):
    incident = Incident.objects.create(
        organization=acme,
        display_id="INC-2026-ED",
        title="Phishing",
        description="Email from other@evil.com was flagged.",
        source_kind="inbound_email",
        source_ref={
            "sender_address": "phisher@evil.com",
            "subject_normalised": "urgent",
            "forwarder_address": "user@corp.com",
        },
    )
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL, value="other@evil.com").exists()


@pytest.mark.django_db
def test_non_phishing_incident_no_email_iocs(acme):
    incident = Incident.objects.create(
        organization=acme,
        display_id="INC-2026-REG",
        title="Wazuh alert: suspicious login from 10.0.0.1",
        description="",
        source_kind="wazuh_event",
        source_ref={"rule_id": "12345"},
    )
    extract_and_save_iocs(incident)
    assert not IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL).exists()


@pytest.mark.django_db
def test_email_ioc_annotation_returns_value(acme):
    from incidents.tasks import _ioc_enrichment_annotation

    incident = _phishing_incident(acme)
    extract_and_save_iocs(incident)
    ioc = IOC.objects.get(incident=incident, kind=IOC.KIND_EMAIL)
    annotation = _ioc_enrichment_annotation(ioc)
    assert annotation == ioc.value


@pytest.mark.django_db
def test_no_duplicate_email_iocs(acme):
    incident = _phishing_incident(acme, sender="phisher@evil.com")
    extract_and_save_iocs(incident)
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_EMAIL, value="phisher@evil.com").count() == 1
