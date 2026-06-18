"""Tests for internet-facing exposure context in the Hunt inventory (PRD #536).

Pure rendering: injected exposures_by_org_agent map, no DB.
"""
from hunts.assets import _exposure_summary, _format_org_section, build_asset_inventory
from hunts.scope import OrgScope
from incidents.services.exposures import Exposure


def _agents(n, prefix="host"):
    return [
        {"id": str(i), "name": f"{prefix}{i}", "ip": f"10.0.0.{i}", "os": "Ubuntu 22.04"}
        for i in range(1, n + 1)
    ]


def _route_exp(fqdn="app.acme.com", port=443):
    return Exposure(
        kind="ingress_route",
        protection="protected",
        specifics={"fqdn": fqdn, "backend_port": port},
    )


def _nat_exp(protocol="tcp", port=3389):
    return Exposure(
        kind="direct_nat",
        protection="raw",
        specifics={"protocol": protocol, "port": port, "public_ip": None, "description": None, "id": 1},
    )


# ── _exposure_summary ─────────────────────────────────────────────────────────


def test_exposure_summary_protected():
    summary = _exposure_summary([_route_exp("myapp.acme.com")])
    assert "protected via myapp.acme.com" in summary


def test_exposure_summary_raw_nat():
    summary = _exposure_summary([_nat_exp(protocol="tcp", port=3389)])
    assert "RAW TCP/3389" in summary


def test_exposure_summary_mixed():
    summary = _exposure_summary([_route_exp(), _nat_exp()])
    assert "protected via" in summary
    assert "RAW TCP" in summary


# ── _format_org_section with exposures ────────────────────────────────────────


def test_internet_facing_agent_annotated_in_section():
    scope = OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))
    exposures_by_agent = {"host1": [_route_exp("app.acme.com")]}

    out = _format_org_section(scope, [], 40, exposures_by_agent=exposures_by_agent)

    assert "host1" in out
    assert "internet-facing" in out
    assert "protected via app.acme.com" in out


def test_non_internet_facing_agent_has_no_annotation():
    scope = OrgScope(1, "Acme", "acme", ["1"], agents=_agents(2))
    exposures_by_agent = {"host1": [_route_exp()]}  # only host1 exposed

    out = _format_org_section(scope, [], 40, exposures_by_agent=exposures_by_agent)

    assert "host1" in out
    assert "host2" in out
    # host2 line has no internet-facing suffix
    lines = out.splitlines()
    host2_line = next(l for l in lines if "host2" in l)
    assert "internet-facing" not in host2_line


def test_raw_nat_in_inventory_annotation():
    scope = OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))
    exposures_by_agent = {"host1": [_nat_exp(port=22)]}

    out = _format_org_section(scope, [], 40, exposures_by_agent=exposures_by_agent)

    assert "RAW TCP/22" in out


# ── build_asset_inventory with injected exposures ─────────────────────────────


def test_build_inventory_with_exposed_agent():
    scope = [OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))]
    exposures_by_org_agent = {1: {"host1": [_route_exp("app.acme.com")]}}

    out = build_asset_inventory(scope, routes_by_org={}, exposures_by_org_agent=exposures_by_org_agent)

    assert "internet-facing" in out
    assert "protected via app.acme.com" in out


def test_build_inventory_agent_without_asset_renders_unchanged():
    scope = [OrgScope(1, "Acme", "acme", ["1"], agents=_agents(1))]
    # No entry for host1 → no internet-facing suffix
    out = build_asset_inventory(scope, routes_by_org={}, exposures_by_org_agent={})

    lines = [l for l in out.splitlines() if "host1" in l]
    assert len(lines) == 1
    assert "internet-facing" not in lines[0]
