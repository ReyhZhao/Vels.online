import pytest
from unittest.mock import patch
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.mark.django_db
def test_first_incident_gets_0001(acme):
    from incidents.services.identifiers import next_display_id
    year = __import__("django.utils.timezone", fromlist=["timezone"]).now().year
    did = next_display_id()
    assert did == f"INC-{year}-0001"


@pytest.mark.django_db
def test_sequential_increments(acme):
    from incidents.services.identifiers import next_display_id
    from incidents.models import Incident

    year = __import__("django.utils.timezone", fromlist=["timezone"]).now().year
    first = next_display_id()
    Incident.objects.create(
        organization=acme, display_id=first, title="First",
    )
    second = next_display_id()
    assert second == f"INC-{year}-0002"


@pytest.mark.django_db
def test_year_reset(acme):
    from incidents.services.identifiers import next_display_id
    from incidents.models import Incident

    Incident.objects.create(
        organization=acme, display_id="INC-2025-0003", title="Old",
    )
    with patch("incidents.services.identifiers.timezone") as mock_tz:
        mock_tz.now.return_value.__class__ = type(__import__("datetime").datetime.now())
        mock_tz.now.return_value = __import__("datetime").datetime(2026, 1, 1)
        did = next_display_id()
    assert did == "INC-2026-0001"


@pytest.mark.django_db
def test_display_id_format(acme):
    from incidents.services.identifiers import next_display_id
    from incidents.models import Incident

    year = __import__("django.utils.timezone", fromlist=["timezone"]).now().year
    for i in range(9):
        did = next_display_id()
        Incident.objects.create(organization=acme, display_id=did, title=f"Inc {i}")

    did = next_display_id()
    assert did == f"INC-{year}-0010"
    parts = did.split("-")
    assert len(parts) == 3
    assert parts[0] == "INC"
    assert len(parts[2]) == 4
