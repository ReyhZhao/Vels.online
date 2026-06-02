import pytest
from incidents.models import Asset, IOC, Incident
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


@pytest.mark.django_db
def test_owned_ip_not_extracted_as_ioc(acme):
    Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="My Server",
        ip_address="192.168.1.55",
        is_active=True,
    )
    inc = Incident.objects.create(
        organization=acme,
        title="Alert on 192.168.1.55",
        description="Traffic from 192.168.1.55",
        display_id="INC-2026-OWN-IP",
    )
    extract_and_save_iocs(inc)
    assert not IOC.objects.filter(incident=inc, kind=IOC.KIND_IP, value="192.168.1.55").exists()


@pytest.mark.django_db
def test_owned_domain_not_extracted_as_ioc(acme):
    from ingress.models import Route

    route = Route.objects.create(
        organization=acme,
        fqdn="myapp.example.com",
        backend_host="myapp",
        backend_port=8080,
    )
    Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_ROUTE,
        name="My App",
        route=route,
        is_active=True,
    )
    inc = Incident.objects.create(
        organization=acme,
        title="Alert",
        description="Traffic to myapp.example.com and https://myapp.example.com/login",
        display_id="INC-2026-OWN-DOM",
    )
    extract_and_save_iocs(inc)
    assert not IOC.objects.filter(incident=inc, kind=IOC.KIND_DOMAIN, value="myapp.example.com").exists()
    assert not IOC.objects.filter(incident=inc, kind=IOC.KIND_URL).filter(value__icontains="myapp.example.com").exists()


@pytest.mark.django_db
def test_non_owned_ip_still_extracted(acme):
    Asset.objects.create(
        organization=acme,
        kind=Asset.KIND_HOST,
        name="My Server",
        ip_address="10.0.0.1",
        is_active=True,
    )
    inc = Incident.objects.create(
        organization=acme,
        title="Alert on 192.168.1.55",
        description="C2 traffic from 192.168.1.55",
        display_id="INC-2026-EXT-IP",
    )
    extract_and_save_iocs(inc)
    assert IOC.objects.filter(incident=inc, kind=IOC.KIND_IP, value="192.168.1.55").exists()
