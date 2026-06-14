"""In-scope asset inventory rendering for the hunt LLM context (#512).

Pure rendering: build_asset_inventory takes a resolved scope (+ an injected routes map)
and produces the known-good asset block. No Wazuh, no OpenSearch, no DB.
"""
from hunts.assets import build_asset_inventory
from hunts.scope import INFRASTRUCTURE_AGENT_ID, OrgScope


def _agents(n, prefix="host"):
    return [
        {"id": str(i), "name": f"{prefix}{i}", "ip": f"10.0.0.{i}", "os": "Ubuntu 22.04"}
        for i in range(1, n + 1)
    ]


def test_empty_scope_renders_nothing():
    assert build_asset_inventory([]) == ""


def test_lists_agents_with_name_ip_and_os():
    scope = [OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))]

    out = build_asset_inventory(scope, routes_by_org={})

    assert "## Acme" in out
    assert "host1 — 10.0.0.1 — Ubuntu 22.04" in out
    # the model is told these are known-good, not attacker infrastructure
    assert "indicators of compromise" in out


def test_includes_ingress_routes_when_provided():
    scope = [OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))]
    routes = {1: [{"fqdn": "app.acme.com", "backend_host": "10.0.0.1", "backend_port": 443}]}

    out = build_asset_inventory(scope, routes_by_org=routes)

    assert "Ingress routes (1):" in out
    assert "app.acme.com -> 10.0.0.1:443" in out


def test_tenant_isolation_each_org_sees_only_its_own_assets():
    scope = [
        OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1, prefix="acme")),
        OrgScope(2, "Globex", "globex", ["2"], agents=_agents(1, prefix="globex")),
    ]
    routes = {
        1: [{"fqdn": "app.acme.com", "backend_host": "10.0.0.1", "backend_port": 443}],
        2: [{"fqdn": "app.globex.com", "backend_host": "10.1.0.1", "backend_port": 443}],
    }

    out = build_asset_inventory(scope, routes_by_org=routes)
    acme_section, globex_section = out.split("## Globex")

    assert "acme1" in acme_section and "globex1" not in acme_section
    assert "app.acme.com" in acme_section and "app.globex.com" not in acme_section
    assert "globex1" in globex_section and "acme1" not in globex_section


def test_agent_list_is_truncated_with_a_remainder_summary():
    scope = [OrgScope(1, "Acme", "acme", [], agents=_agents(50))]

    out = build_asset_inventory(scope, routes_by_org={}, max_agents_per_org=5)

    assert "Agents (50):" in out
    assert "host5 — 10.0.0.5" in out
    assert "host6 — 10.0.0.6" not in out
    assert "… and 45 more agent(s)" in out


def test_infrastructure_org_section_has_no_agent_list_and_does_not_error():
    scope = [
        OrgScope(9, "Shared Infrastructure", "", [INFRASTRUCTURE_AGENT_ID],
                 is_infrastructure=True),
    ]

    out = build_asset_inventory(scope, routes_by_org={})

    assert "## Shared Infrastructure" in out
    assert "Shared infrastructure" in out
    assert "Agents (" not in out


def test_org_with_no_agents_available_renders_a_placeholder():
    scope = [OrgScope(1, "Acme", "acme", [], agents=[])]

    out = build_asset_inventory(scope, routes_by_org={})

    assert "## Acme" in out
    assert "Agents: none available." in out
