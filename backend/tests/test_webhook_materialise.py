"""Webhook Ingest Endpoints slices #745/#747/#748: the Materialiser's per-type write
semantics (CONTEXT.md → Ingest Endpoint; ADR-0040)."""

import pytest

from alerts.models import Alert
from incidents.models import Asset, Incident
from security.models import Organization
from webhook_ingest.materialise import materialise
from webhook_ingest.models import IngestEndpoint


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def _endpoint(org, target, **over):
    return IngestEndpoint.objects.create(
        name=f"{target} ep", target_type=target, organization=org, **over
    )


@pytest.mark.django_db
def test_incident_created_with_webhook_source_kind(acme):
    ep = _endpoint(acme, "incident")
    obj, kind, err = materialise(ep, {"title": "Ransomware note", "severity": "high"})
    assert err == "" and kind == "incident"
    inc = Incident.objects.get(pk=obj.pk)
    assert inc.source_kind == Incident.SOURCE_WEBHOOK
    assert inc.organization == acme
    assert inc.title == "Ransomware note"
    assert inc.display_id.startswith("INC-")


@pytest.mark.django_db
def test_alert_created_through_ecs_path_with_entities(acme):
    ep = _endpoint(acme, "alert")
    fields = {"title": "SSH brute", "severity": "high", "entities": {"source.ip": "10.0.0.9"}}
    obj, kind, err = materialise(ep, fields)
    assert err == "" and kind == "alert"
    alert = Alert.objects.get(pk=obj.pk)
    assert alert.source_kind == "webhook"
    # It ran through the ECS-entity path, so the entity row exists (enables correlation).
    assert alert.entities.filter(entity_type="source.ip", value="10.0.0.9").exists()


@pytest.mark.django_db
def test_alert_with_no_entity_fails(acme):
    ep = _endpoint(acme, "alert")
    obj, kind, err = materialise(ep, {"title": "no entity", "entities": {}})
    assert obj is None
    assert "no recognised ECS entity" in err
    assert not Alert.objects.exists()


@pytest.mark.django_db
def test_asset_upserts_on_name(acme):
    ep = _endpoint(acme, "asset")
    obj1, _, err1 = materialise(ep, {"name": "web01", "ip_address": "10.0.0.1"})
    obj2, _, err2 = materialise(ep, {"name": "web01", "ip_address": "10.0.0.2"})
    assert err1 == "" and err2 == ""
    # A re-post updates the same Asset rather than creating a duplicate.
    assert obj1.pk == obj2.pk
    assert Asset.objects.filter(organization=acme, name="web01").count() == 1
    obj2.refresh_from_db()
    assert obj2.ip_address == "10.0.0.2"
    # Webhook assets leave the Wazuh agent_name NULL so they never collide with agents.
    assert obj2.agent_name is None


@pytest.mark.django_db
def test_asset_missing_identity_fails(acme):
    ep = _endpoint(acme, "asset")
    obj, kind, err = materialise(ep, {"ip_address": "10.0.0.3"})
    assert obj is None
    assert "identity field" in err
