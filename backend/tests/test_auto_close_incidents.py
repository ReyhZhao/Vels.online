from datetime import timedelta

import pytest
from django.utils import timezone

from incidents.models import Incident, IncidentEvent
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def make_incident(acme, state, days_old):
    inc = Incident.objects.create(
        organization=acme,
        title="Test",
        tlp="amber",
        display_id=f"INC-TEST-{Incident.objects.count() + 1:04d}",
        state=state,
    )
    # backdating created_at requires a direct update since auto_now_add is set
    Incident.objects.filter(pk=inc.pk).update(created_at=timezone.now() - timedelta(days=days_old))
    inc.refresh_from_db()
    return inc


@pytest.mark.django_db
def test_stale_new_incident_is_closed(acme):
    from incidents.tasks import auto_close_stale_incidents

    stale = make_incident(acme, Incident.STATE_NEW, days_old=8)
    result = auto_close_stale_incidents()
    stale.refresh_from_db()

    assert stale.state == Incident.STATE_CLOSED
    assert result["closed"] == 1


@pytest.mark.django_db
def test_stale_triaged_incident_is_closed(acme):
    from incidents.tasks import auto_close_stale_incidents

    stale = make_incident(acme, Incident.STATE_TRIAGED, days_old=8)
    auto_close_stale_incidents()
    stale.refresh_from_db()

    assert stale.state == Incident.STATE_CLOSED


@pytest.mark.django_db
def test_stale_resolved_incident_is_closed(acme):
    from incidents.tasks import auto_close_stale_incidents

    stale = make_incident(acme, Incident.STATE_RESOLVED, days_old=8)
    auto_close_stale_incidents()
    stale.refresh_from_db()

    assert stale.state == Incident.STATE_CLOSED


@pytest.mark.django_db
def test_fresh_incident_is_not_closed(acme):
    from incidents.tasks import auto_close_stale_incidents

    fresh = make_incident(acme, Incident.STATE_NEW, days_old=3)
    result = auto_close_stale_incidents()
    fresh.refresh_from_db()

    assert fresh.state == Incident.STATE_NEW
    assert result["closed"] == 0


@pytest.mark.django_db
def test_in_progress_incident_is_not_closed(acme):
    from incidents.tasks import auto_close_stale_incidents

    in_progress = make_incident(acme, Incident.STATE_IN_PROGRESS, days_old=30)
    auto_close_stale_incidents()
    in_progress.refresh_from_db()

    assert in_progress.state == Incident.STATE_IN_PROGRESS


@pytest.mark.django_db
def test_already_closed_incident_is_not_touched(acme):
    from incidents.tasks import auto_close_stale_incidents

    closed = make_incident(acme, Incident.STATE_CLOSED, days_old=30)
    result = auto_close_stale_incidents()

    assert result["closed"] == 0


@pytest.mark.django_db
def test_auto_close_records_timeline_event(acme):
    from incidents.tasks import auto_close_stale_incidents

    stale = make_incident(acme, Incident.STATE_NEW, days_old=8)
    auto_close_stale_incidents()

    assert IncidentEvent.objects.filter(incident=stale, kind="auto_closed").exists()
