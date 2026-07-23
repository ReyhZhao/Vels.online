"""Webhook Ingest Endpoints slices #745/#746/#749: the async processor (mapping →
materialise → per-element outcomes → aggregate status), idempotency, and Replay."""

import pytest

from incidents.models import Incident
from security.models import Organization
from webhook_ingest import replay
from webhook_ingest.models import CapturedPayload, IngestEndpoint, PayloadElementOutcome
from webhook_ingest.processing import process_payload


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def _incident_endpoint(org, **over):
    cfg = dict(
        name="Splunk incidents",
        target_type="incident",
        organization=org,
        state=IngestEndpoint.STATE_ACTIVE,
        collection_root_path="results",
        idempotency_key_path="id",
        field_mappings={"title": {"kind": "path", "path": "name"}},
    )
    cfg.update(over)
    return IngestEndpoint.objects.create(**cfg)


@pytest.mark.django_db
def test_batch_all_valid_yields_created_and_n_records(acme):
    ep = _incident_endpoint(acme)
    payload = CapturedPayload.objects.create(
        endpoint=ep,
        body={"results": [{"id": "a", "name": "One"}, {"id": "b", "name": "Two"}]},
    )
    status = process_payload(payload)
    assert status == CapturedPayload.STATUS_CREATED
    assert Incident.objects.filter(source_kind=Incident.SOURCE_WEBHOOK).count() == 2
    assert payload.outcomes.filter(outcome="created").count() == 2


@pytest.mark.django_db
def test_batch_mixed_validity_is_partial(acme):
    # title mapping missing on the second element (no "name") → serializer rejects it.
    ep = _incident_endpoint(acme)
    payload = CapturedPayload.objects.create(
        endpoint=ep,
        body={"results": [{"id": "a", "name": "Good"}, {"id": "b"}]},
    )
    status = process_payload(payload)
    assert status == CapturedPayload.STATUS_PARTIAL
    assert payload.outcomes.filter(outcome="created").count() == 1
    assert payload.outcomes.filter(outcome="failed").count() == 1


@pytest.mark.django_db
def test_empty_mapping_result_is_failed(acme):
    ep = _incident_endpoint(acme, collection_root_path="nonexistent")
    payload = CapturedPayload.objects.create(endpoint=ep, body={"results": [{"id": "a"}]})
    assert process_payload(payload) == CapturedPayload.STATUS_FAILED


@pytest.mark.django_db
def test_idempotency_key_suppresses_duplicate_create(acme):
    ep = _incident_endpoint(acme)
    body = {"results": [{"id": "dup", "name": "Once"}]}
    p1 = CapturedPayload.objects.create(endpoint=ep, body=body)
    p2 = CapturedPayload.objects.create(endpoint=ep, body=body)
    process_payload(p1)
    process_payload(p2)
    # Second post with the same idempotency key creates no second Incident.
    assert Incident.objects.filter(source_kind=Incident.SOURCE_WEBHOOK).count() == 1
    assert p2.outcomes.filter(outcome="skipped").count() == 1


@pytest.mark.django_db
def test_replay_reworks_failed_elements_and_skips_created(acme):
    ep = _incident_endpoint(acme)
    payload = CapturedPayload.objects.create(
        endpoint=ep,
        body={"results": [{"id": "a", "name": "Good"}, {"id": "b"}]},  # 2nd fails first pass
    )
    assert process_payload(payload) == CapturedPayload.STATUS_PARTIAL
    assert Incident.objects.count() == 1

    # Fix the failed element by editing the body's second element, then replay.
    payload.body = {"results": [{"id": "a", "name": "Good"}, {"id": "b", "name": "Fixed"}]}
    payload.save(update_fields=["body"])
    results = replay.replay_endpoint(ep)

    assert results == [{"captured_payload": payload.id, "status": CapturedPayload.STATUS_CREATED}]
    # The already-created first element was not duplicated; only the failed one was worked.
    assert Incident.objects.filter(source_kind=Incident.SOURCE_WEBHOOK).count() == 2


@pytest.mark.django_db
def test_replay_preview_commits_nothing(acme):
    ep = _incident_endpoint(acme)
    CapturedPayload.objects.create(endpoint=ep, body={"results": [{"id": "a", "name": "One"}]})
    preview = replay.preview_endpoint(ep)
    assert preview["payloads"] == 1
    assert preview["elements_to_attempt"] == 1
    assert Incident.objects.count() == 0  # dry run created nothing
