"""Hunt lens tools — tenant-scoped query layer (module 2, issues #476/#480/#554).

Asserts external behaviour: a cross-org sweep fans out per tenant (one query per org,
scoped to *that org's* agents and never mixing tenants), records Findings tagged with the
right org, and the behavioural lenses honour scope + allowlists. Drives the lenses with a
fake OpenSearch client and a list-collecting findings sink — no infrastructure.
"""
import pytest

from hunts.lenses import (
    HuntContext, build_hunt_lenses, build_general_query_tools, _ALERTS_INDEX,
)
from hunts.scope import OrgScope


class FakeOS:
    def __init__(self, hits_per_call=None, aggs_per_call=None, mapping=None):
        self.calls = []
        self._hits = hits_per_call or []
        self._aggs = aggs_per_call or []
        self._mapping = mapping or {}

    def _search(self, index, body):
        i = len(self.calls)
        self.calls.append((index, body))
        out = {"hits": {"hits": self._hits[i] if i < len(self._hits) else []}}
        if i < len(self._aggs):
            out["aggregations"] = self._aggs[i]
        return out

    def get_field_mapping(self):
        return self._mapping


def _agent_ids_in(body):
    return body["query"]["bool"]["filter"][0]["terms"]["agent.id"]


def _ctx(scope, os_client, sink=None):
    return HuntContext(scope=scope, lookback_days=30, os_client=os_client, record_findings=sink)


def _lens(tools, name):
    return next(t for t in tools if t.name == name)


TWO_ORGS = [
    OrgScope(org_id=1, org_name="Acme", wazuh_group="acme", agent_ids=["1", "2"]),
    OrgScope(org_id=2, org_name="Beta", wazuh_group="beta", agent_ids=["9"]),
]


def test_ioc_search_fans_out_one_query_per_tenant_never_mixing_agents():
    os_client = FakeOS(hits_per_call=[
        [{"_id": "a", "_index": "wazuh-alerts", "_source": {"rule": {"description": "mal"}}}],  # Acme
        [],  # Beta
    ])
    recorded = []
    ctx = _ctx(TWO_ORGS, os_client, sink=lambda s, lens, hits: recorded.append((s.org_id, lens, hits)))
    tool = _lens(build_hunt_lenses(ctx), "ioc_search")

    result = tool.executor({"ioc_type": "hash", "value": "deadbeef"})

    # one query per org, each scoped only to that org's agents
    assert len(os_client.calls) == 2
    assert _agent_ids_in(os_client.calls[0][1]) == ["1", "2"]
    assert _agent_ids_in(os_client.calls[1][1]) == ["9"]
    # no single query ever mixes tenants
    for _index, body in os_client.calls:
        ids = set(_agent_ids_in(body))
        assert ids in ({"1", "2"}, {"9"})
    # findings recorded only for the org that matched, tagged with that org
    assert [r[0] for r in recorded] == [1]
    assert result.content["total_matches"] == 1
    assert result.content["by_org"] == [{"organization": "Acme", "count": 1}]


def test_ioc_search_queries_infrastructure_with_positive_000_filter():
    """An all-orgs sweep reaches the Infrastructure scope via a positive agent.id="000"
    term (never by dropping the agent filter), recording infra findings (issue #494)."""
    infra = OrgScope(
        org_id=7, org_name="Shared Infrastructure", wazuh_group="",
        agent_ids=["000"], is_infrastructure=True,
    )
    os_client = FakeOS(hits_per_call=[
        [],  # Acme
        [],  # Beta
        [{"_id": "fw", "_index": "wazuh-alerts", "_source": {"rule": {"description": "fw drop"}}}],  # infra
    ])
    recorded = []
    ctx = _ctx(TWO_ORGS + [infra], os_client, sink=lambda s, lens, hits: recorded.append((s.org_id, hits)))
    tool = _lens(build_hunt_lenses(ctx), "ioc_search")

    result = tool.executor({"ioc_type": "ip", "value": "1.2.3.4"})

    # the infra query carries a positive agent.id="000" terms filter
    assert _agent_ids_in(os_client.calls[2][1]) == ["000"]
    # the firewall match is recorded as a finding attributed to the infra org
    assert (7, os_client._hits[2]) in recorded
    assert {"organization": "Shared Infrastructure", "count": 1} in result.content["by_org"]


def test_ioc_search_skips_orgs_with_no_agents():
    scope = [OrgScope(1, "Acme", "acme", ["1"]), OrgScope(2, "Empty", "empty", [])]
    os_client = FakeOS(hits_per_call=[[]])
    ctx = _ctx(scope, os_client, sink=lambda *a: None)
    tool = _lens(build_hunt_lenses(ctx), "ioc_search")

    tool.executor({"ioc_type": "ip", "value": "1.2.3.4"})

    assert len(os_client.calls) == 1  # the empty org is never queried


def test_ioc_search_rejects_bad_args_without_querying():
    os_client = FakeOS()
    ctx = _ctx(TWO_ORGS, os_client, sink=lambda *a: None)
    tool = _lens(build_hunt_lenses(ctx), "ioc_search")

    result = tool.executor({"ioc_type": "nonsense", "value": "x"})

    assert result.error is not None
    assert os_client.calls == []


def test_ioc_search_uses_the_alerts_index_and_lookback_window():
    os_client = FakeOS(hits_per_call=[[]])
    ctx = HuntContext(scope=[TWO_ORGS[0]], lookback_days=7, os_client=os_client,
                      record_findings=lambda *a: None)
    tool = _lens(build_hunt_lenses(ctx), "ioc_search")

    tool.executor({"ioc_type": "domain", "value": "evil.test"})

    index, body = os_client.calls[0]
    assert index == _ALERTS_INDEX
    assert body["query"]["bool"]["filter"][1]["range"]["@timestamp"]["gte"] == "now-7d"


def test_agent_activity_only_queries_the_owning_org():
    os_client = FakeOS(hits_per_call=[[{"_id": "e", "_index": "i", "_source": {}}]])
    recorded = []
    ctx = _ctx(TWO_ORGS, os_client, sink=lambda s, lens, hits: recorded.append(s.org_id))
    tool = _lens(build_hunt_lenses(ctx), "agent_activity")

    result = tool.executor({"agent_id": "9"})  # belongs to Beta only

    assert len(os_client.calls) == 1
    assert recorded == [2]
    assert result.content["agent_id"] == "9"


def test_top_values_rejects_non_allowlisted_field():
    os_client = FakeOS()
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_hunt_lenses(ctx), "top_values")

    result = tool.executor({"field": "data.secret"})

    assert result.error is not None
    assert os_client.calls == []


# ── IT Hygiene Inventory lenses (ADR-0022) ──────────────────────────────────────

def _inv_hit(agent_id, agent_name, name):
    return {"_id": f"{agent_id}-{name}", "_index": "wazuh-states-inventory-packages-wazuh",
            "_source": {"agent": {"id": agent_id, "name": agent_name},
                        "package": {"name": name, "version": "1.0"}}}


def test_inventory_search_fans_out_per_tenant_and_records_no_findings():
    os_client = FakeOS(hits_per_call=[
        [_inv_hit("1", "WEB-01", "evilpkg"), _inv_hit("2", "WEB-02", "evilpkg")],  # Acme
        [],  # Beta
    ])
    recorded = []
    ctx = _ctx(TWO_ORGS, os_client, sink=lambda *a, **k: recorded.append(a))
    tool = _lens(build_hunt_lenses(ctx), "inventory_search")

    result = tool.executor({"kind": "software", "query": "evilpkg"})

    # one query per org, each scoped only to that org's agents, against the packages index
    assert len(os_client.calls) == 2
    assert os_client.calls[0][0] == "wazuh-states-inventory-packages-*"
    assert _agent_ids_in(os_client.calls[0][1]) == ["1", "2"]
    assert _agent_ids_in(os_client.calls[1][1]) == ["9"]
    # summary-only: NOTHING is ever recorded
    assert recorded == []
    # matching hosts + counts surfaced per org
    assert result.content["total_matches"] == 2
    assert result.content["by_org"] == [
        {"organization": "Acme", "count": 2, "hosts": ["WEB-01", "WEB-02"]},
    ]


def test_inventory_search_rejects_bad_kind_and_empty_query_without_querying():
    os_client = FakeOS()
    ctx = _ctx(TWO_ORGS, os_client, sink=lambda *a, **k: None)
    tool = _lens(build_hunt_lenses(ctx), "inventory_search")

    assert tool.executor({"kind": "packages", "query": "x"}).error is not None
    assert tool.executor({"kind": "software", "query": "  "}).error is not None
    assert os_client.calls == []


def test_record_inventory_finding_resolves_host_and_records_with_model_summary():
    scope = [
        OrgScope(org_id=1, org_name="Acme", wazuh_group="acme", agent_ids=["1", "2"],
                 agents=[{"id": "1", "name": "WEB-01"}, {"id": "2", "name": "WEB-02"}]),
        OrgScope(org_id=2, org_name="Beta", wazuh_group="beta", agent_ids=["9"],
                 agents=[{"id": "9", "name": "BETA-1"}]),
    ]
    os_client = FakeOS(hits_per_call=[[_inv_hit("1", "WEB-01", "evilpkg")]])
    recorded = []
    ctx = _ctx(scope, os_client,
               sink=lambda s, lens, hits, summary=None: recorded.append((s.org_id, lens, hits, summary)))
    tool = _lens(build_hunt_lenses(ctx), "record_inventory_finding")

    result = tool.executor({"agent_name": "WEB-01", "kind": "software",
                            "name": "evilpkg", "summary": "compromised evilpkg 1.0 on WEB-01"})

    # the precise doc is re-queried, scoped to the resolved host only
    assert _agent_ids_in(os_client.calls[0][1]) == ["1"]
    # recorded to the owning org, carrying the model-supplied summary
    assert len(recorded) == 1
    org_id, lens, hits, summary = recorded[0]
    assert org_id == 1 and lens == "record_inventory_finding"
    assert summary == "compromised evilpkg 1.0 on WEB-01"
    assert result.content["recorded"] == 1


def test_record_inventory_finding_rejects_out_of_scope_host():
    scope = [OrgScope(org_id=1, org_name="Acme", wazuh_group="acme", agent_ids=["1"],
                      agents=[{"id": "1", "name": "WEB-01"}])]
    os_client = FakeOS()
    ctx = _ctx(scope, os_client, sink=lambda *a, **k: None)
    tool = _lens(build_hunt_lenses(ctx), "record_inventory_finding")

    result = tool.executor({"agent_name": "GHOST-9", "kind": "software",
                            "name": "x", "summary": "y"})

    assert result.error is not None
    assert os_client.calls == []  # never queried for an out-of-scope host


def test_record_inventory_finding_requires_a_summary():
    scope = [OrgScope(org_id=1, org_name="Acme", wazuh_group="acme", agent_ids=["1"],
                      agents=[{"id": "1", "name": "WEB-01"}])]
    ctx = _ctx(scope, FakeOS(), sink=lambda *a, **k: None)
    tool = _lens(build_hunt_lenses(ctx), "record_inventory_finding")
    assert tool.executor({"agent_name": "WEB-01", "kind": "software", "name": "x"}).error is not None


def test_record_inventory_finding_commits_nothing_under_the_scoping_sink():
    scope = [OrgScope(org_id=1, org_name="Acme", wazuh_group="acme", agent_ids=["1"],
                      agents=[{"id": "1", "name": "WEB-01"}])]
    os_client = FakeOS(hits_per_call=[[_inv_hit("1", "WEB-01", "evilpkg")]])
    # Scoping phase: record_findings is None (non-persisting sink, ADR-0018)
    ctx = HuntContext(scope=scope, lookback_days=30, os_client=os_client, record_findings=None)
    tool = _lens(build_hunt_lenses(ctx), "record_inventory_finding")

    result = tool.executor({"agent_name": "WEB-01", "kind": "software",
                            "name": "evilpkg", "summary": "bad"})

    assert result.error is None
    assert result.content["recorded"] == 0
    assert result.content["scoping"] is True
    assert os_client.calls == []  # nothing even queried in scoping


def test_top_rules_fans_out_and_aggregates_per_org():
    os_client = FakeOS(aggs_per_call=[
        {"by_rule": {"buckets": [{"key": "brute force", "doc_count": 5}]}},
        {"by_rule": {"buckets": []}},
    ])
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_hunt_lenses(ctx), "top_rules")

    result = tool.executor({})

    assert len(os_client.calls) == 2
    assert result.content["by_org"][0]["organization"] == "Acme"
    assert result.content["by_org"][0]["top_rules"] == [{"rule": "brute force", "count": 5}]


# ── Aggregation grammar compiler (ADR-0026) ─────────────────────────────────────

from correlations.services.search_compiler import compile_hunt_agg_query  # noqa: E402


def test_compile_hunt_agg_count_no_groups_tracks_total_hits():
    body, err = compile_hunt_agg_query(
        filters=[], group_by=[], metric={"type": "count"}, interval=None,
        agent_ids=["1", "2"], lookback_days=7,
    )
    assert err is None
    assert body["size"] == 0
    assert body["track_total_hits"] is True
    assert body["query"]["bool"]["filter"][0]["terms"]["agent.id"] == ["1", "2"]
    assert "now-7d" in body["query"]["bool"]["filter"][1]["range"]["@timestamp"]["gte"]
    assert "aggs" not in body


def test_compile_hunt_agg_count_one_group():
    mapping = {"data.srcip": "ip"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["data.srcip"], metric={"type": "count"}, interval=None,
        agent_ids=["1"], lookback_days=30, field_mapping=mapping,
    )
    assert err is None
    assert "group0" in body["aggs"]
    assert body["aggs"]["group0"]["terms"]["field"] == "data.srcip"
    assert body["aggs"]["group0"]["terms"]["size"] == 20
    assert "aggs" not in body["aggs"]["group0"]


def test_compile_hunt_agg_sum_two_groups_nested():
    mapping = {"data.srcip": "ip", "agent.name": "keyword", "bytes": "long"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["data.srcip", "agent.name"],
        metric={"type": "sum", "field": "bytes"}, interval=None,
        agent_ids=["1"], lookback_days=30, field_mapping=mapping,
    )
    assert err is None
    g0 = body["aggs"]["group0"]
    assert g0["terms"]["field"] == "data.srcip"
    g1 = g0["aggs"]["group1"]
    assert g1["terms"]["field"] == "agent.name"
    assert g1["aggs"]["metric"] == {"sum": {"field": "bytes"}}


def test_compile_hunt_agg_cardinality():
    mapping = {"data.srcip": "ip", "data.dstport": "long"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["data.srcip"],
        metric={"type": "cardinality", "field": "data.dstport"},
        interval=None, agent_ids=["1"], lookback_days=30, field_mapping=mapping,
    )
    assert err is None
    assert body["aggs"]["group0"]["aggs"]["metric"] == {"cardinality": {"field": "data.dstport"}}


def test_compile_hunt_agg_avg():
    mapping = {"agent.name": "keyword", "bytes": "long"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["agent.name"],
        metric={"type": "avg", "field": "bytes"},
        interval=None, agent_ids=["1"], lookback_days=30, field_mapping=mapping,
    )
    assert err is None
    assert body["aggs"]["group0"]["aggs"]["metric"] == {"avg": {"field": "bytes"}}


def test_compile_hunt_agg_interval_wraps_groups():
    mapping = {"rule.description": "text", "rule.description.keyword": "keyword"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["rule.description"], metric={"type": "count"}, interval="1d",
        agent_ids=["1"], lookback_days=30, field_mapping=mapping,
    )
    assert err is None
    over_time = body["aggs"]["over_time"]
    assert over_time["date_histogram"]["fixed_interval"] == "1d"
    assert "group0" in over_time["aggs"]
    # text field resolved to .keyword
    assert over_time["aggs"]["group0"]["terms"]["field"] == "rule.description.keyword"


def test_compile_hunt_agg_interval_only_no_groups():
    body, err = compile_hunt_agg_query(
        filters=[], group_by=[], metric={"type": "count"}, interval="6h",
        agent_ids=["1"], lookback_days=30,
    )
    assert err is None
    assert body["aggs"]["over_time"]["date_histogram"]["fixed_interval"] == "6h"
    assert "aggs" not in body["aggs"]["over_time"]


def test_compile_hunt_agg_filter_condition_included():
    mapping = {"data.srcip": "ip", "rule.level": "long"}
    body, err = compile_hunt_agg_query(
        filters=[{"field": "data.srcip", "operator": "equals", "value": "1.2.3.4"}],
        group_by=["rule.level"], metric={"type": "count"}, interval=None,
        agent_ids=["1"], lookback_days=7, field_mapping=mapping,
    )
    assert err is None
    q_filters = body["query"]["bool"]["filter"]
    assert any("term" in c and "data.srcip" in c["term"] for c in q_filters)


def test_compile_hunt_agg_clamps_outer_size_to_50():
    mapping = {"f": "keyword"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["f"], metric={"type": "count"}, interval=None,
        agent_ids=["1"], lookback_days=7, field_mapping=mapping, outer_size=200,
    )
    assert err is None
    assert body["aggs"]["group0"]["terms"]["size"] == 50


def test_compile_hunt_agg_clamps_inner_size_to_20():
    mapping = {"f1": "keyword", "f2": "keyword"}
    body, err = compile_hunt_agg_query(
        filters=[], group_by=["f1", "f2"], metric={"type": "count"}, interval=None,
        agent_ids=["1"], lookback_days=7, field_mapping=mapping,
        outer_size=50, inner_size=100,
    )
    assert err is None
    assert body["aggs"]["group0"]["aggs"]["group1"]["terms"]["size"] == 20


def test_compile_hunt_agg_rejects_more_than_two_groups():
    _, err = compile_hunt_agg_query(
        filters=[], group_by=["a", "b", "c"], metric={"type": "count"}, interval=None,
        agent_ids=[], lookback_days=7,
    )
    assert err is not None
    assert "group_by" in err


def test_compile_hunt_agg_rejects_invalid_interval():
    _, err = compile_hunt_agg_query(
        filters=[], group_by=[], metric={"type": "count"}, interval="7d",
        agent_ids=[], lookback_days=7,
    )
    assert err is not None
    assert "interval" in err


def test_compile_hunt_agg_rejects_non_aggregatable_text_group_by():
    mapping = {"desc": "text"}  # text with no .keyword subfield
    _, err = compile_hunt_agg_query(
        filters=[], group_by=["desc"], metric={"type": "count"}, interval=None,
        agent_ids=[], lookback_days=7, field_mapping=mapping,
    )
    assert err is not None


def test_compile_hunt_agg_rejects_non_numeric_sum():
    mapping = {"rule.description": "text"}
    _, err = compile_hunt_agg_query(
        filters=[], group_by=[], metric={"type": "sum", "field": "rule.description"},
        interval=None, agent_ids=[], lookback_days=7, field_mapping=mapping,
    )
    assert err is not None


def test_compile_hunt_agg_rejects_unknown_group_by_field():
    mapping = {"known": "keyword"}
    _, err = compile_hunt_agg_query(
        filters=[], group_by=["unknown_field"], metric={"type": "count"},
        interval=None, agent_ids=[], lookback_days=7, field_mapping=mapping,
    )
    assert err is not None
    assert "unknown_field" in err


def test_compile_hunt_agg_rejects_invalid_metric_type():
    _, err = compile_hunt_agg_query(
        filters=[], group_by=[], metric={"type": "median"},
        interval=None, agent_ids=[], lookback_days=7,
    )
    assert err is not None
    assert "metric.type" in err


def test_compile_hunt_agg_rejects_bad_filter_operator():
    mapping = {"rule.level": "long"}
    _, err = compile_hunt_agg_query(
        filters=[{"field": "rule.level", "operator": "contains", "value": "5"}],
        group_by=[], metric={"type": "count"}, interval=None,
        agent_ids=[], lookback_days=7, field_mapping=mapping,
    )
    assert err is not None
    assert "Filter condition error" in err


# ── search_events lens (ADR-0026) ───────────────────────────────────────────────

def test_search_events_fans_out_one_query_per_org_and_never_records_findings():
    aggs = {"group0": {"buckets": [{"key": "10.0.0.1", "doc_count": 42}]}}
    os_client = FakeOS(
        aggs_per_call=[aggs, {}],
        mapping={"data.srcip": "ip"},
    )
    recorded = []
    ctx = HuntContext(
        scope=TWO_ORGS, lookback_days=30, os_client=os_client,
        record_findings=lambda *a, **k: recorded.append(a),
    )
    tool = _lens(build_general_query_tools(ctx), "search_events")

    result = tool.executor({
        "filters": [],
        "group_by": ["data.srcip"],
        "metric": {"type": "count"},
    })

    # one query per org (two orgs with agents)
    assert len(os_client.calls) == 2
    # each query is scoped to that org's agents only
    assert os_client.calls[0][1]["query"]["bool"]["filter"][0]["terms"]["agent.id"] == ["1", "2"]
    assert os_client.calls[1][1]["query"]["bool"]["filter"][0]["terms"]["agent.id"] == ["9"]
    # by_org output
    assert result.content["by_org"][0]["organization"] == "Acme"
    assert result.content["by_org"][0]["aggregations"] == aggs
    # NEVER records any findings
    assert recorded == []


def test_search_events_skips_orgs_with_no_agents():
    scope = [OrgScope(1, "Acme", "acme", ["1"]), OrgScope(2, "Empty", "empty", [])]
    os_client = FakeOS(aggs_per_call=[{}], mapping={"f": "keyword"})
    ctx = HuntContext(scope=scope, lookback_days=30, os_client=os_client)
    tool = _lens(build_general_query_tools(ctx), "search_events")

    tool.executor({"group_by": ["f"], "metric": {"type": "count"}})

    assert len(os_client.calls) == 1  # empty org is never queried


def test_search_events_rejects_invalid_group_by_field():
    os_client = FakeOS(mapping={"known": "keyword"})
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_general_query_tools(ctx), "search_events")

    result = tool.executor({"group_by": ["nonexistent_field"], "metric": {"type": "count"}})

    assert result.error is not None
    assert os_client.calls == []  # never queries on bad args


def test_search_events_rejects_invalid_metric_type():
    os_client = FakeOS(mapping={})
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_general_query_tools(ctx), "search_events")

    result = tool.executor({"metric": {"type": "stdev"}})

    assert result.error is not None
    assert os_client.calls == []


def test_search_events_passes_bucket_size_from_context():
    mapping = {"f": "keyword"}
    os_client = FakeOS(aggs_per_call=[{}, {}], mapping=mapping)
    ctx = HuntContext(scope=TWO_ORGS, lookback_days=30, os_client=os_client, max_buckets=5)
    tool = _lens(build_general_query_tools(ctx), "search_events")

    tool.executor({"group_by": ["f"], "metric": {"type": "count"}})

    body = os_client.calls[0][1]
    assert body["aggs"]["group0"]["terms"]["size"] == 5


def test_search_events_commits_no_findings_even_with_sink():
    os_client = FakeOS(aggs_per_call=[{"g": {"buckets": [{"key": "x", "doc_count": 1}]}}])
    recorded = []
    ctx = HuntContext(
        scope=[TWO_ORGS[0]], lookback_days=30, os_client=os_client,
        record_findings=lambda *a, **k: recorded.append(a),
    )
    tool = _lens(build_general_query_tools(ctx), "search_events")

    tool.executor({"metric": {"type": "count"}})

    assert recorded == []


# ── describe_fields lens (ADR-0026) ─────────────────────────────────────────────

def test_describe_fields_returns_schema_only_no_values():
    mapping = {"agent.id": "keyword", "data.srcip": "ip", "rule.level": "long"}
    os_client = FakeOS(mapping=mapping)
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_general_query_tools(ctx), "describe_fields")

    result = tool.executor({})

    assert result.error is None
    assert result.content["count"] == 3
    names = [f["name"] for f in result.content["fields"]]
    assert set(names) == {"agent.id", "data.srcip", "rule.level"}
    # no values from the index — only names and types
    assert all(set(f.keys()) == {"name", "type"} for f in result.content["fields"])


def test_describe_fields_prefix_filter():
    mapping = {
        "data.srcip": "ip", "data.dstip": "ip",
        "rule.level": "long", "rule.description": "text",
        "agent.name": "keyword",
    }
    os_client = FakeOS(mapping=mapping)
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_general_query_tools(ctx), "describe_fields")

    result = tool.executor({"prefix": "rule."})

    names = {f["name"] for f in result.content["fields"]}
    assert names == {"rule.level", "rule.description"}
    assert result.content["count"] == 2


def test_describe_fields_empty_prefix_returns_all():
    mapping = {"a": "keyword", "b": "long", "c": "ip"}
    os_client = FakeOS(mapping=mapping)
    ctx = _ctx(TWO_ORGS, os_client)
    tool = _lens(build_general_query_tools(ctx), "describe_fields")

    result = tool.executor({"prefix": ""})

    assert result.content["count"] == 3


# ── Capability gating (ADR-0026) ─────────────────────────────────────────────────

class _CapableProvider:
    def supports_complex_tools(self):
        return True


class _WeakProvider:
    def supports_complex_tools(self):
        return False


def test_build_hunt_lenses_includes_general_query_for_capable_provider():
    ctx = _ctx(TWO_ORGS, FakeOS())
    tools = build_hunt_lenses(ctx, provider=_CapableProvider())
    names = {t.name for t in tools}
    assert "search_events" in names
    assert "describe_fields" in names


def test_build_hunt_lenses_excludes_general_query_for_weak_provider():
    ctx = _ctx(TWO_ORGS, FakeOS())
    tools = build_hunt_lenses(ctx, provider=_WeakProvider())
    names = {t.name for t in tools}
    assert "search_events" not in names
    assert "describe_fields" not in names
    # fixed lenses still present
    assert "ioc_search" in names
    assert "top_rules" in names


def test_build_hunt_lenses_excludes_general_query_when_no_provider():
    ctx = _ctx(TWO_ORGS, FakeOS())
    tools = build_hunt_lenses(ctx)
    names = {t.name for t in tools}
    assert "search_events" not in names
    assert "describe_fields" not in names
