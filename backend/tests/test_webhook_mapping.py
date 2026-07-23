"""Webhook Ingest Endpoints slice #743: the pure Field Mapping engine (CONTEXT.md → Field
Mapping; ADR-0040). No DB — exhaustive unit tests over config + body."""

from webhook_ingest import mapping


def test_resolve_path_dotted_and_array_index():
    body = {"result": {"host": "web01"}, "events": [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}]}
    assert mapping.resolve_path(body, "result.host") == "web01"
    assert mapping.resolve_path(body, "events.1.ip") == "2.2.2.2"
    assert mapping.resolve_path(body, "result.missing") is None
    assert mapping.resolve_path(body, "events.9.ip") is None
    assert mapping.resolve_path(body, "") is None


def test_resolve_field_path_then_value_map_case_insensitive():
    cfg = {"kind": "path", "path": "sev", "value_map": {"P1": "critical"}}
    assert mapping.resolve_field(cfg, {"sev": "p1"}, field_name="severity") == "critical"


def test_resolve_field_default_when_path_missing():
    cfg = {"kind": "path", "path": "sev", "default": "medium"}
    assert mapping.resolve_field(cfg, {}, field_name="severity") == "medium"


def test_resolve_field_constant():
    cfg = {"kind": "constant", "value": "amber"}
    assert mapping.resolve_field(cfg, {"anything": 1}, field_name="tlp") == "amber"


def test_resolve_field_enum_drops_invalid_value():
    cfg = {"kind": "path", "path": "sev"}
    # "bogus" is not a severity enum member → dropped so the serializer default applies.
    assert mapping.resolve_field(cfg, {"sev": "bogus"}, field_name="severity") is None


def test_fan_out_without_collection_root_is_single_element():
    body = {"title": "one"}
    assert mapping.fan_out("", body) == [body]


def test_fan_out_over_collection_root_array():
    body = {"results": [{"n": 1}, {"n": 2}, {"n": 3}]}
    assert mapping.fan_out("results", body) == [{"n": 1}, {"n": 2}, {"n": 3}]


def test_fan_out_non_list_yields_no_elements():
    assert mapping.fan_out("results", {"results": "not-a-list"}) == []


def test_resolve_fans_splunk_batch_into_per_element_payloads():
    config = {
        "collection_root_path": "results",
        "field_mappings": {
            "title": {"kind": "path", "path": "search_name"},
            "severity": {"kind": "path", "path": "sev", "value_map": {"crit": "critical"}},
        },
    }
    body = {"results": [
        {"search_name": "Brute force", "sev": "crit"},
        {"search_name": "Port scan", "sev": "low"},
    ]}
    resolved = mapping.resolve(config, body, "incident")
    assert len(resolved) == 2
    assert resolved[0]["fields"] == {"title": "Brute force", "severity": "critical"}
    assert resolved[1]["fields"] == {"title": "Port scan", "severity": "low"}


def test_resolve_alert_assembles_ecs_entities():
    config = {
        "field_mappings": {"title": {"kind": "path", "path": "rule"}},
        "entity_mappings": {
            "source.ip": {"kind": "path", "path": "src"},
            "host.name": {"kind": "path", "path": "host"},
            "bogus.field": {"kind": "constant", "value": "x"},  # unknown ECS field → ignored
        },
    }
    body = {"rule": "SSH", "src": "10.0.0.9", "host": "db01"}
    resolved = mapping.resolve(config, body, "alert")
    assert resolved[0]["fields"]["entities"] == {"source.ip": "10.0.0.9", "host.name": "db01"}


def test_resolve_alert_with_no_entity_paths_gives_empty_envelope():
    config = {"field_mappings": {"title": {"kind": "constant", "value": "x"}}, "entity_mappings": {}}
    resolved = mapping.resolve(config, {"a": 1}, "alert")
    assert resolved[0]["fields"]["entities"] == {}


def test_idempotency_key_prefers_configured_path():
    config = {"idempotency_key_path": "id"}
    assert mapping.idempotency_key_for(config, {"id": "abc-123"}) == "abc-123"


def test_idempotency_key_falls_back_to_content_hash():
    config = {"idempotency_key_path": ""}
    k1 = mapping.idempotency_key_for(config, {"a": 1, "b": 2})
    k2 = mapping.idempotency_key_for(config, {"b": 2, "a": 1})  # order-independent
    k3 = mapping.idempotency_key_for(config, {"a": 1, "b": 3})
    assert k1.startswith("sha256:")
    assert k1 == k2
    assert k1 != k3
