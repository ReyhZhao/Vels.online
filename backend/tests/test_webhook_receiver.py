"""Webhook Ingest Endpoints slices #741/#742/#743/#750: the public receiver guard matrix,
Capturing no-op, staff-only management, dry-run preview, and retention purge."""

import json
import uuid

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from incidents.models import Incident
from security.models import Organization
from webhook_ingest.models import CapturedPayload, IngestEndpoint


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _endpoint(org, **over):
    cfg = dict(name="ep", target_type="incident", organization=org)
    cfg.update(over)
    return IngestEndpoint.objects.create(**cfg)


def _post(client, path_uuid, body, raw=None):
    data = raw if raw is not None else json.dumps(body)
    return client.post(f"/ingest/{path_uuid}/", data=data, content_type="application/json")


@pytest.mark.django_db
def test_receiver_accepts_and_caches_returns_202(acme):
    ep = _endpoint(acme)
    resp = _post(APIClient(), ep.path_uuid, {"hello": "world"})
    assert resp.status_code == 202
    payload = CapturedPayload.objects.get(endpoint=ep)
    assert payload.body == {"hello": "world"}
    assert payload.status == CapturedPayload.STATUS_PENDING


@pytest.mark.django_db
def test_receiver_unknown_uuid_returns_404(acme):
    resp = _post(APIClient(), uuid.uuid4(), {"a": 1})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_receiver_paused_endpoint_returns_404(acme):
    ep = _endpoint(acme, state=IngestEndpoint.STATE_PAUSED)
    resp = _post(APIClient(), ep.path_uuid, {"a": 1})
    assert resp.status_code == 404
    assert not CapturedPayload.objects.exists()


@pytest.mark.django_db
def test_receiver_oversize_returns_413(acme):
    ep = _endpoint(acme, max_body_bytes=10)
    resp = _post(APIClient(), ep.path_uuid, {"a": "x" * 100})
    assert resp.status_code == 413
    assert not CapturedPayload.objects.exists()


@pytest.mark.django_db
def test_receiver_malformed_json_returns_400_not_cached(acme):
    ep = _endpoint(acme)
    resp = _post(APIClient(), ep.path_uuid, None, raw="{not valid json")
    assert resp.status_code == 400
    assert not CapturedPayload.objects.exists()


@pytest.mark.django_db
def test_receiver_rate_limit_returns_429(acme):
    ep = _endpoint(acme, rate_limit_per_minute=2)
    client = APIClient()
    assert _post(client, ep.path_uuid, {"n": 1}).status_code == 202
    assert _post(client, ep.path_uuid, {"n": 2}).status_code == 202
    assert _post(client, ep.path_uuid, {"n": 3}).status_code == 429


@pytest.mark.django_db
def test_capturing_endpoint_materialises_nothing(acme):
    from webhook_ingest.tasks import process_captured_payload

    ep = _endpoint(acme, state=IngestEndpoint.STATE_CAPTURING,
                   field_mappings={"title": {"kind": "path", "path": "t"}})
    payload = CapturedPayload.objects.create(endpoint=ep, body={"t": "hi"})
    process_captured_payload(payload.id)  # task runs, but endpoint is Capturing
    payload.refresh_from_db()
    assert payload.status == CapturedPayload.STATUS_PENDING
    assert not Incident.objects.exists()


@pytest.mark.django_db
def test_management_is_staff_only(acme):
    assert APIClient().get("/api/ingest-endpoints/endpoints/").status_code in (401, 403)


@pytest.mark.django_db
def test_staff_can_create_endpoint_and_get_url(acme, staff):
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.post(
        "/api/ingest-endpoints/endpoints/",
        {"name": "Splunk", "target_type": "incident", "organization": acme.id},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["state"] == "capturing"
    assert resp.data["ingest_path"].startswith("/ingest/")


@pytest.mark.django_db
def test_dry_run_previews_mapping_over_sample(acme, staff):
    ep = _endpoint(acme, field_mappings={"title": {"kind": "path", "path": "name"}})
    payload = CapturedPayload.objects.create(endpoint=ep, body={"name": "Preview me"})
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.post(
        f"/api/ingest-endpoints/endpoints/{ep.id}/dry-run/",
        {"captured_payload": payload.id},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["elements"][0]["fields"] == {"title": "Preview me"}
    assert not Incident.objects.exists()  # dry run only


@pytest.mark.django_db
def test_activate_requires_mapping_then_activates(acme, staff):
    ep = _endpoint(acme)  # no field_mappings yet
    client = APIClient()
    client.force_authenticate(staff)
    r1 = client.post(f"/api/ingest-endpoints/endpoints/{ep.id}/activate/")
    assert r1.status_code == 400

    ep.field_mappings = {"title": {"kind": "constant", "value": "x"}}
    ep.save(update_fields=["field_mappings"])
    r2 = client.post(f"/api/ingest-endpoints/endpoints/{ep.id}/activate/")
    assert r2.status_code == 200
    assert r2.data["endpoint"]["state"] == "active"
    assert "replay_preview" in r2.data


@pytest.mark.django_db
def test_purge_removes_aged_payloads(acme):
    from datetime import timedelta

    from django.utils import timezone

    from webhook_ingest.tasks import purge_captured_payloads

    ep = _endpoint(acme, retention_days=30)
    fresh = CapturedPayload.objects.create(endpoint=ep, body={"a": 1})
    old = CapturedPayload.objects.create(endpoint=ep, body={"a": 2})
    CapturedPayload.objects.filter(pk=old.pk).update(
        received_at=timezone.now() - timedelta(days=31)
    )
    deleted = purge_captured_payloads()
    assert deleted == 1
    assert CapturedPayload.objects.filter(pk=fresh.pk).exists()
    assert not CapturedPayload.objects.filter(pk=old.pk).exists()
