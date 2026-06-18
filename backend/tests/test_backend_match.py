"""Unit tests for the backend matcher (PRD #536).

Pure function — no DB required.
"""
from ingress.services.backend_match import match_backend_to_asset


class _Route:
    def __init__(self, backend_host, backend_type="direct"):
        self.backend_host = backend_host
        self.backend_type = backend_type


class _Asset:
    def __init__(self, pk, name, agent_name=None, ip_address=None):
        self.pk = pk
        self.name = name
        self.agent_name = agent_name
        self.ip_address = ip_address


def test_single_exact_ip_match_returns_auto_match():
    route = _Route("10.0.0.1")
    asset = _Asset(1, "srv-01", ip_address="10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [asset])
    assert auto is asset
    assert suggestions == []


def test_multiple_ip_matches_no_auto_match():
    route = _Route("10.0.0.1")
    a1 = _Asset(1, "srv-01", ip_address="10.0.0.1")
    a2 = _Asset(2, "srv-02", ip_address="10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [a1, a2])
    assert auto is None


def test_no_ip_match_returns_none():
    route = _Route("10.0.0.99")
    asset = _Asset(1, "srv-01", ip_address="10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [asset])
    assert auto is None
    assert suggestions == []


def test_name_only_match_produces_suggestion_no_auto_link():
    route = _Route("srv-01")
    asset = _Asset(1, "srv-01", agent_name="srv-01", ip_address="192.168.1.1")
    auto, suggestions = match_backend_to_asset(route, [asset])
    assert auto is None
    assert asset in suggestions


def test_agent_name_match_produces_suggestion():
    route = _Route("myhost")
    asset = _Asset(1, "srv", agent_name="myhost", ip_address=None)
    auto, suggestions = match_backend_to_asset(route, [asset])
    assert auto is None
    assert asset in suggestions


def test_netbird_route_returns_neither():
    route = _Route("10.0.0.1", backend_type="netbird")
    asset = _Asset(1, "srv-01", ip_address="10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [asset])
    assert auto is None
    assert suggestions == []


def test_ip_match_asset_not_in_suggestions():
    route = _Route("10.0.0.1")
    asset = _Asset(1, "10.0.0.1", agent_name="10.0.0.1", ip_address="10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [asset])
    # exact IP match → auto_match, not suggestion
    assert auto is asset
    assert asset not in suggestions


def test_empty_candidates_returns_none():
    route = _Route("10.0.0.1")
    auto, suggestions = match_backend_to_asset(route, [])
    assert auto is None
    assert suggestions == []
