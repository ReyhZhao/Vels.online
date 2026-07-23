"""Materialiser / adapter for webhook Ingest Endpoints (CONTEXT.md → Ingest Endpoint;
ADR-0040).

`materialise(endpoint, fields) -> (obj, kind, error)` hands a mapped element payload to the
*same* internal create path the platform already uses — it invents no new creation path.
Write semantics are per target type: Incident/Alert create-new; Asset upserts on its
identity field (default ``name``). Idempotency dedup for the create-new types is handled by
the caller (see tasks.process_payload); Asset upsert is inherently convergent.
"""

from django.db import transaction


def _materialise_incident(endpoint, fields):
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.identifiers import next_display_id

    data = dict(fields)
    data["source_kind"] = "webhook"
    ser = IncidentCreateSerializer(data=data)
    if not ser.is_valid():
        return None, "incident", f"invalid incident: {ser.errors}"
    with transaction.atomic():
        incident = ser.save(
            organization=endpoint.organization,
            display_id=next_display_id(),
            created_by=None,
        )
    return incident, "incident", ""


def _materialise_alert(endpoint, fields):
    """Create an Alert through the existing ingest path so it is wrapped in the ECS entity
    envelope and run through correlation (ADR-0040). An element with no recognised ECS
    entity fails, matching the V2 ingest contract."""
    from alerts.models import STATE_NEW, Alert
    from alerts.services.entities import entities_for
    from alerts.services.identifiers import next_alert_display_id

    envelope = fields.get("entities") or {}
    if not entities_for({"entities": envelope}):
        return None, "alert", "alert has no recognised ECS entity"

    with transaction.atomic():
        alert = Alert.objects.create(
            organization=endpoint.organization,
            display_id=next_alert_display_id(),
            source_kind="webhook",
            source_ref={},
            title=fields.get("title") or None,
            severity=fields.get("severity") or None,
            description=fields.get("description") or None,
            pap=fields.get("pap") or None,
            tlp=fields.get("tlp") or None,
            state=STATE_NEW,
        )
        _save_alert_entities(alert, endpoint.organization, envelope)
        aid = alert.id
        transaction.on_commit(lambda: _enqueue_correlation_eval(aid))
    return alert, "alert", ""


def _save_alert_entities(alert, org, envelope):
    from alerts.models import AlertEntity
    from alerts.services.entities import entities_for

    for entity_type, value in entities_for({"entities": envelope}):
        AlertEntity.objects.create(
            alert=alert, organization=org, entity_type=entity_type, value=value
        )


def _enqueue_correlation_eval(alert_id):
    from correlations.tasks import evaluate_correlation_rules

    evaluate_correlation_rules.delay(alert_id)


def _materialise_asset(endpoint, fields):
    """Upsert a host Asset on its identity field within the endpoint's org (ADR-0040). Wazuh
    ``agent_name`` is left NULL so a webhook asset never collides with an agent-discovered
    host asset. Race-guarded because ``name`` carries no DB uniqueness constraint."""
    from incidents.models import Asset

    identity_field = endpoint.identity_field or "name"
    identity_value = fields.get(identity_field)
    if not identity_value:
        return None, "asset", f"asset is missing its identity field '{identity_field}'"

    updatable = {k: v for k, v in fields.items() if k in ("name", "ip_address", "role")}

    with transaction.atomic():
        existing = (
            Asset.objects.select_for_update()
            .filter(organization=endpoint.organization, kind=Asset.KIND_HOST, **{identity_field: identity_value})
            .first()
        )
        if existing:
            changed = []
            for k, v in updatable.items():
                if getattr(existing, k) != v:
                    setattr(existing, k, v)
                    changed.append(k)
            if changed:
                existing.save(update_fields=changed)
            return existing, "asset", ""
        asset = Asset.objects.create(
            organization=endpoint.organization,
            kind=Asset.KIND_HOST,
            agent_name=None,
            **updatable,
        )
    return asset, "asset", ""


_DISPATCH = {
    "incident": _materialise_incident,
    "alert": _materialise_alert,
    "asset": _materialise_asset,
}


def materialise(endpoint, fields):
    """Create (or, for assets, upsert) the target record from a mapped element payload.
    Returns ``(obj_or_None, kind, error_str)``."""
    handler = _DISPATCH.get(endpoint.target_type)
    if handler is None:
        return None, endpoint.target_type, f"unknown target type '{endpoint.target_type}'"
    try:
        return handler(endpoint, fields)
    except Exception as exc:  # a bad mapping must dead-letter the element, never 500 the worker
        return None, endpoint.target_type, f"{type(exc).__name__}: {exc}"
