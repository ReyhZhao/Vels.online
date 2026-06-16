"""Hunt lens tools — tenant-scoped query layer (module 2, issues #476/#480).

Asserts external behaviour: a cross-org sweep fans out per tenant (one query per org,
scoped to *that org's* agents and never mixing tenants), records Findings tagged with the
right org, and the behavioural lenses honour scope + allowlists. Drives the lenses with a
fake OpenSearch client and a list-collecting findings sink — no infrastructure.
"""
import pytest

from hunts.lenses import HuntContext, build_hunt_lenses, _ALERTS_INDEX
from hunts.scope import OrgScope


class FakeOS:
    def __init__(self, hits_per_call=None, aggs_per_call=None):
        self.calls = []
        self._hits = hits_per_call or []
        self._aggs = aggs_per_call or []

    def _search(self, index, body):
        i = len(self.calls)
        self.calls.append((index, body))
        out = {"hits": {"hits": self._hits[i] if i < len(self._hits) else []}}
        if i < len(self._aggs):
            out["aggregations"] = self._aggs[i]
        return out


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
