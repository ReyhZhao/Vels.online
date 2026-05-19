import pytest
from incidents.models import IOC, Incident
from incidents.services.ioc_extraction import extract_and_save_iocs
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(acme):
    return Incident.objects.create(
        organization=acme,
        title="Malware from 192.168.1.55",
        description="C2 traffic to evil.com and https://malware.example.com/payload.exe",
        display_id="INC-2026-TEST",
    )


@pytest.mark.django_db
def test_extracts_ips(incident):
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_IP, value="192.168.1.55").exists()


@pytest.mark.django_db
def test_extracts_domains(incident):
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_DOMAIN).exists()


@pytest.mark.django_db
def test_extracts_urls(incident):
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_URL).exists()


@pytest.mark.django_db
def test_no_duplicates_on_double_call(incident):
    extract_and_save_iocs(incident)
    extract_and_save_iocs(incident)
    assert IOC.objects.filter(incident=incident, kind=IOC.KIND_IP, value="192.168.1.55").count() == 1


@pytest.mark.django_db
def test_no_iocs_when_clean_text(acme):
    clean = Incident.objects.create(
        organization=acme,
        title="User reported suspicious login",
        description="No indicators present in this report.",
        display_id="INC-2026-CLEAN",
    )
    extract_and_save_iocs(clean)
    assert IOC.objects.filter(incident=clean).count() == 0
