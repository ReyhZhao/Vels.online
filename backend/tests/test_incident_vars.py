import json
from unittest.mock import MagicMock

import pytest

from automations.incident_vars import UnresolvableVarError, resolve_incident_vars


def _make_asset(kind="host", agent_name=None, ip_address=None):
    a = MagicMock()
    a.kind = kind
    a.agent_name = agent_name
    a.ip_address = ip_address
    return a


def _make_ioc(kind, value):
    ioc = MagicMock()
    ioc.kind = kind
    ioc.value = value
    return ioc


def _make_incident(title="Test", severity="medium", assets=(), iocs=()):
    inc = MagicMock()
    inc.title = title
    inc.severity = severity
    inc.assets.all.return_value = list(assets)
    inc.iocs.all.return_value = list(iocs)
    return inc


# ── source resolution ─────────────────────────────────────────────────────────


def test_assets_agent_name_single():
    inc = _make_incident(assets=[_make_asset(agent_name="agent1")])
    result = resolve_incident_vars("- {var: hosts, source: assets.agent_name}", inc)
    assert result == {"hosts": "agent1"}


def test_assets_agent_name_multiple_colon_separated():
    inc = _make_incident(
        assets=[_make_asset(agent_name="agent1"), _make_asset(agent_name="agent2")]
    )
    result = resolve_incident_vars("- {var: hosts, source: assets.agent_name}", inc)
    assert result == {"hosts": "agent1:agent2"}


def test_assets_ip_address():
    inc = _make_incident(assets=[_make_asset(ip_address="10.0.0.1"), _make_asset(ip_address="10.0.0.2")])
    result = resolve_incident_vars("- {var: ips, source: assets.ip_address}", inc)
    assert result == {"ips": "10.0.0.1:10.0.0.2"}


def test_assets_skips_non_host_assets():
    inc = _make_incident(
        assets=[_make_asset(kind="route", agent_name="route-agent"), _make_asset(agent_name="real")]
    )
    result = resolve_incident_vars("- {var: h, source: assets.agent_name}", inc)
    assert result == {"h": "real"}


def test_iocs_ip():
    inc = _make_incident(iocs=[_make_ioc("ip", "1.2.3.4"), _make_ioc("domain", "evil.com")])
    result = resolve_incident_vars("- {var: block_ips, source: iocs.ip}", inc)
    assert result == {"block_ips": "1.2.3.4"}


def test_iocs_domain():
    inc = _make_incident(iocs=[_make_ioc("domain", "a.com"), _make_ioc("domain", "b.com")])
    result = resolve_incident_vars("- {var: domains, source: iocs.domain}", inc)
    assert result == {"domains": "a.com:b.com"}


def test_iocs_url():
    inc = _make_incident(iocs=[_make_ioc("url", "http://evil.com/path")])
    result = resolve_incident_vars("- {var: urls, source: iocs.url}", inc)
    assert result == {"urls": "http://evil.com/path"}


def test_incident_title():
    inc = _make_incident(title="Ransomware Alert")
    result = resolve_incident_vars("- {var: title, source: incident.title}", inc)
    assert result == {"title": "Ransomware Alert"}


def test_incident_severity():
    inc = _make_incident(severity="critical")
    result = resolve_incident_vars("- {var: sev, source: incident.severity}", inc)
    assert result == {"sev": "critical"}


# ── format serialization ──────────────────────────────────────────────────────


def test_comma_separated():
    inc = _make_incident(assets=[_make_asset(agent_name="a1"), _make_asset(agent_name="a2")])
    yaml_str = "- {var: hosts, source: assets.agent_name, format: comma_separated}"
    result = resolve_incident_vars(yaml_str, inc)
    assert result == {"hosts": "a1,a2"}


def test_json_array():
    inc = _make_incident(iocs=[_make_ioc("ip", "1.2.3.4"), _make_ioc("ip", "5.6.7.8")])
    yaml_str = "- {var: block_ips, source: iocs.ip, format: json_array}"
    result = resolve_incident_vars(yaml_str, inc)
    assert result == {"block_ips": json.dumps(["1.2.3.4", "5.6.7.8"])}


def test_format_ignored_for_scalar_incident_title():
    inc = _make_incident(title="My Title")
    yaml_str = "- {var: t, source: incident.title, format: comma_separated}"
    result = resolve_incident_vars(yaml_str, inc)
    assert result == {"t": "My Title"}


def test_format_ignored_for_scalar_incident_severity():
    inc = _make_incident(severity="low")
    yaml_str = "- {var: s, source: incident.severity, format: json_array}"
    result = resolve_incident_vars(yaml_str, inc)
    assert result == {"s": "low"}


# ── zero-values error ─────────────────────────────────────────────────────────


def test_unresolvable_var_error_for_empty_assets():
    inc = _make_incident(assets=[])
    with pytest.raises(UnresolvableVarError) as exc_info:
        resolve_incident_vars("- {var: hosts, source: assets.agent_name}", inc)
    err = exc_info.value
    assert err.var_name == "hosts"
    assert err.source == "assets.agent_name"
    assert "hosts" in str(err)
    assert "assets.agent_name" in str(err)


def test_unresolvable_var_error_for_empty_iocs():
    inc = _make_incident(iocs=[])
    with pytest.raises(UnresolvableVarError) as exc_info:
        resolve_incident_vars("- {var: bad_ips, source: iocs.ip}", inc)
    assert exc_info.value.var_name == "bad_ips"


# ── multiple mappings ─────────────────────────────────────────────────────────


def test_multiple_mappings_resolved_in_one_call():
    inc = _make_incident(
        title="Alert",
        severity="high",
        assets=[_make_asset(agent_name="wazuh1")],
        iocs=[_make_ioc("ip", "9.9.9.9")],
    )
    yaml_str = """
- {var: hosts, source: assets.agent_name}
- {var: block_ips, source: iocs.ip}
- {var: title, source: incident.title}
- {var: sev, source: incident.severity}
"""
    result = resolve_incident_vars(yaml_str, inc)
    assert result == {
        "hosts": "wazuh1",
        "block_ips": "9.9.9.9",
        "title": "Alert",
        "sev": "high",
    }
