from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from alerts.models import Alert
from api.public_stats import CACHE_KEY
from correlations.models import CorrelationRule
from incidents.models import Asset, Incident
from security.models import Organization

URL = "/api/public/stats/"


@pytest.fixture(autouse=True)
def clear_stats_cache():
    cache.delete(CACHE_KEY)
    yield
    cache.delete(CACHE_KEY)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.mark.django_db
def test_reachable_without_authentication(client):
    response = client.get(URL)
    assert response.status_code == 200


@pytest.mark.django_db
def test_counts_recent_alerts_and_ignores_older_ones(client, org):
    Alert.objects.create(
        organization=org, display_id="AL-0001", source_kind="wazuh", title="recent"
    )
    old = Alert.objects.create(
        organization=org, display_id="AL-0002", source_kind="wazuh", title="old"
    )
    Alert.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=45)
    )

    body = client.get(URL).json()

    assert body["alerts_ingested"] == 1
    assert body["window_days"] == 30


@pytest.mark.django_db
def test_counts_resolved_and_closed_incidents(client, org):
    Incident.objects.create(
        organization=org, display_id="INC-0001", title="resolved", state=Incident.STATE_RESOLVED
    )
    Incident.objects.create(
        organization=org, display_id="INC-0002", title="closed", state=Incident.STATE_CLOSED
    )
    Incident.objects.create(
        organization=org, display_id="INC-0003", title="open", state=Incident.STATE_NEW
    )

    assert client.get(URL).json()["incidents_resolved"] == 2


@pytest.mark.django_db
def test_counts_only_active_host_assets(client, org):
    Asset.objects.create(organization=org, name="host-a", kind=Asset.KIND_HOST, is_active=True)
    Asset.objects.create(organization=org, name="host-b", kind=Asset.KIND_HOST, is_active=False)
    Asset.objects.create(organization=org, name="www.acme.test", kind=Asset.KIND_ROUTE, is_active=True)

    assert client.get(URL).json()["endpoints_monitored"] == 1


@pytest.mark.django_db
def test_excludes_the_infrastructure_pseudo_org_from_the_tenant_count(client, org):
    # The migration-seeded Infrastructure org owns no customer (ADR-0017); only
    # `org` should be counted.
    assert Organization.objects.count() == 2

    assert client.get(URL).json()["organizations_protected"] == 1


@pytest.mark.django_db
def test_counts_enabled_detection_rules(client, org):
    CorrelationRule.objects.create(organization=org, name="live", enabled=True)
    CorrelationRule.objects.create(organization=org, name="off", enabled=False)

    assert client.get(URL).json()["detection_rules_live"] == 1


@pytest.mark.django_db
def test_exposes_no_tenant_identifying_data(client, org):
    body = client.get(URL).json()

    assert set(body) == {
        "window_days",
        "alerts_ingested",
        "incidents_resolved",
        "endpoints_monitored",
        "organizations_protected",
        "detection_rules_live",
        "generated_at",
    }
    assert "Acme" not in response_text(body)
    assert "acme" not in response_text(body)


def response_text(body):
    return " ".join(str(v) for v in body.values())


@pytest.mark.django_db
def test_response_is_cached_between_requests(client, org):
    first = client.get(URL).json()
    assert first["alerts_ingested"] == 0

    Alert.objects.create(
        organization=org, display_id="AL-0001", source_kind="wazuh", title="after the cache filled"
    )

    # Still the cached figure — the new alert is not counted until the TTL lapses.
    assert client.get(URL).json()["alerts_ingested"] == 0

    cache.delete(CACHE_KEY)
    assert client.get(URL).json()["alerts_ingested"] == 1
