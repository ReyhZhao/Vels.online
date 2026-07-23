"""Pure Field Mapping engine for webhook Ingest Endpoints (CONTEXT.md → Field Mapping;
ADR-0040). The webhook sibling of ``partners/mapping.py``.

`resolve(endpoint_config, body, target_type)` turns a sender's JSON body into a list of
canonical element payloads. Per field the precedence mirrors the email path with
regex→JSON-path:

    resolve path (or constant) → value_map (case-insensitive) → default → enum-match

No DB, no network — a pure function over the endpoint's mapping config and the raw body, so
it is exhaustively unit-testable. Templates (`kind == "template"`) are a reserved future
form and are not resolved here.
"""

import hashlib
import json

# Valid target-enum values, mirroring the model choices. Duplicated here (not imported) to
# keep this module pure and model-free.
_ENUMS = {
    "severity": {"critical", "high", "medium", "low", "info"},
    "tlp": {"white", "green", "amber", "red"},
    "pap": {"white", "green", "amber", "red"},
}

# Canonical fields the mapping may target, per resource type.
TARGET_FIELDS = {
    "incident": ("title", "description", "severity", "tlp", "pap"),
    "alert": ("title", "description", "severity", "tlp", "pap"),
    "asset": ("name", "ip_address", "role"),
}

# Recognised ECS entity fields an Alert mapping may target (mirrors alerts.services.entities).
ECS_FIELDS = ("host.name", "source.ip", "user.name", "file.hash.sha256", "process.name")


def resolve_path(body, path):
    """Return the value at a dotted JSON ``path`` in ``body`` (array indices allowed, e.g.
    ``results.0.host``), or ``None`` if any segment is missing. Never raises."""
    if not path:
        return None
    cur = body
    for seg in str(path).split("."):
        if isinstance(cur, dict):
            if seg not in cur:
                return None
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                idx = int(seg)
            except (TypeError, ValueError):
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            return None
    return cur


def fan_out(collection_root_path, body):
    """Split a body into the elements to map. With no Collection Root the whole body is one
    element; with one, each item of the pointed-at array is an element. A Collection Root
    that does not resolve to a list yields no elements (the payload will fail)."""
    if not collection_root_path:
        return [body]
    arr = resolve_path(body, collection_root_path)
    if isinstance(arr, list):
        return list(arr)
    return []


def _coerce_scalar(value):
    """A resolved leaf used as a field value: keep strings; stringify scalars; reject
    containers (a dict/list is not a field value)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def resolve_field(field_cfg, element, field_name=None):
    """Resolve one target field to a string (or ``None`` to fall back to a serializer default).

    A ``constant`` returns its literal. A ``path`` reads the leaf, applies a case-insensitive
    ``value_map``, then ``default``; for enum fields a value that is not a valid enum member is
    dropped (``None``) so the serializer's own default applies."""
    field_cfg = field_cfg or {}
    kind = field_cfg.get("kind", "path")

    if kind == "constant":
        raw = _coerce_scalar(field_cfg.get("value"))
    else:  # "path" (default); "template" is reserved and treated as unset for now
        raw = _coerce_scalar(resolve_path(element, field_cfg.get("path")))
        if raw is not None:
            value_map = field_cfg.get("value_map") or {}
            if value_map:
                lowered = {str(k).lower(): v for k, v in value_map.items()}
                if raw.lower() in lowered:
                    raw = str(lowered[raw.lower()])

    if raw is None:
        default = field_cfg.get("default")
        raw = str(default) if default not in (None, "") else None

    if raw is None:
        return None
    raw = raw.strip()
    enum = _ENUMS.get(field_name)
    if enum is not None:
        return raw.lower() if raw.lower() in enum else None
    return raw or None


def resolve_element(config, element, target_type):
    """Build the canonical field dict for one element. For an Alert also assembles the ECS
    ``entities`` envelope from ``entity_mappings``."""
    field_mappings = config.get("field_mappings") or {}
    fields = {}
    for name in TARGET_FIELDS.get(target_type, ()):
        cfg = field_mappings.get(name)
        if not cfg:
            continue
        value = resolve_field(cfg, element, field_name=name)
        if value is not None:
            fields[name] = value

    if target_type == "alert":
        entities = {}
        for ecs_field, cfg in (config.get("entity_mappings") or {}).items():
            if ecs_field not in ECS_FIELDS:
                continue
            value = resolve_field(cfg, element, field_name=None)
            if value:
                entities[ecs_field] = value
        fields["entities"] = entities
    return fields


def idempotency_key_for(config, element):
    """The per-element dedup key: the configured idempotency-key path's value, else a stable
    content hash of the element (CONTEXT.md → Collection Root)."""
    path = config.get("idempotency_key_path") or ""
    if path:
        value = _coerce_scalar(resolve_path(element, path))
        if value:
            return value
    blob = json.dumps(element, sort_keys=True, default=str, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resolve(config, body, target_type):
    """Fan a body into elements and resolve each. Returns a list of
    ``{"index", "element", "fields", "idempotency_key"}`` dicts — the payloads the
    materialiser consumes. Pure: commits nothing."""
    result = []
    for index, element in enumerate(fan_out(config.get("collection_root_path") or "", body)):
        result.append(
            {
                "index": index,
                "element": element,
                "fields": resolve_element(config, element, target_type),
                "idempotency_key": idempotency_key_for(config, element),
            }
        )
    return result


def config_from_endpoint(endpoint):
    """The mapping config dict the engine needs, read off an IngestEndpoint (or a draft dict
    for the dry-run preview)."""
    return {
        "collection_root_path": endpoint.collection_root_path,
        "idempotency_key_path": endpoint.idempotency_key_path,
        "field_mappings": endpoint.field_mappings,
        "entity_mappings": endpoint.entity_mappings,
    }
