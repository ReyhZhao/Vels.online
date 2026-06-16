"""IT Hygiene Inventory query core + agent resolution (ADR-0022, modules 1 & 5).

Pure external-behaviour tests: assert the index pattern per kind, the query body's
agent.id scoping + name match + cap, the per-kind projection, and the org-restricted
host name -> agent id resolution. No infrastructure.
"""
from security.inventory import (
    INVENTORY_KINDS, build_inventory_query, index_for, is_valid_kind,
    name_field_for, project_hit, project_hits, resolve_host_agent_ids,
)


def _agent_ids(body):
    return body["query"]["bool"]["filter"][0]["terms"]["agent.id"]


# ── index + kind ──────────────────────────────────────────────────────────────

def test_kind_maps_to_the_right_inventory_index():
    assert index_for("software") == "wazuh-states-inventory-packages-*"
    assert index_for("process") == "wazuh-states-inventory-processes-*"
    assert index_for("service") == "wazuh-states-inventory-services-*"


def test_is_valid_kind_rejects_unknown_kinds():
    assert is_valid_kind("software") and is_valid_kind("process") and is_valid_kind("service")
    assert not is_valid_kind("packages")
    assert not is_valid_kind("")
    assert not is_valid_kind(None)
    assert set(INVENTORY_KINDS) == {"software", "service", "process"}


# ── query body ──────────────────────────────────────────────────────────────

def test_query_scopes_to_agent_ids_and_caps_and_projects():
    body = build_inventory_query("software", ["1", "2"], size=25)
    assert _agent_ids(body) == ["1", "2"]
    assert body["size"] == 25
    # only the allowlisted package fields + agent identity are fetched
    assert set(body["_source"]) == {
        "package.name", "package.version", "package.vendor", "package.architecture",
        "agent.id", "agent.name", "host.name",
    }
    # no name match when none requested
    assert len(body["query"]["bool"]["filter"]) == 1


def test_query_coerces_agent_ids_to_strings():
    assert _agent_ids(build_inventory_query("process", [1, 2])) == ["1", "2"]


def test_name_query_adds_case_insensitive_substring_match_on_the_name_field():
    body = build_inventory_query("process", ["9"], name="MimiKatz")
    name_clause = body["query"]["bool"]["filter"][1]["wildcard"]
    assert name_field_for("process") == "process.name"
    assert name_clause["process.name"]["value"] == "*MimiKatz*"
    assert name_clause["process.name"]["case_insensitive"] is True


def test_service_projection_uses_service_fields():
    body = build_inventory_query("service", ["1"])
    assert "service.start_type" in body["_source"]
    assert "service.state" in body["_source"]


# ── projection ─────────────────────────────────────────────────────────────

def test_project_hit_strips_kind_prefix_and_keeps_agent_identity():
    hit = {"_source": {
        "agent": {"id": "3", "name": "WEB-01"},
        "package": {"name": "openssl", "version": "3.0.1", "vendor": "OpenSSL",
                    "architecture": "x86_64"},
    }}
    row = project_hit("software", hit)
    assert row == {
        "agent_id": "3", "agent_name": "WEB-01",
        "name": "openssl", "version": "3.0.1", "vendor": "OpenSSL", "architecture": "x86_64",
    }


def test_project_hit_handles_nested_process_user_without_colliding_with_process_name():
    hit = {"_source": {
        "agent": {"id": "9", "name": "DB-1"},
        "process": {"name": "sshd", "pid": 42, "executable": "/usr/sbin/sshd",
                    "args": "-D", "user": {"name": "root"}},
    }}
    row = project_hit("process", hit)
    assert row["name"] == "sshd"          # process.name -> name
    assert row["user.name"] == "root"     # process.user.name -> user.name (no collision)
    assert row["executable"] == "/usr/sbin/sshd"


def test_project_hit_tolerates_missing_fields():
    row = project_hit("software", {"_source": {"agent": {"id": "1"}}})
    assert row["agent_id"] == "1"
    assert row["name"] is None
    assert project_hits("software", []) == []


# ── agent resolution (module 5, tenant boundary) ─────────────────────────────

class FakeWazuh:
    """Returns agents per group; records which group was asked for."""
    def __init__(self, by_group):
        self.by_group = by_group
        self.asked = []

    def get_agents(self, group):
        self.asked.append(group)
        return self.by_group.get(group, [])


def test_resolve_host_agent_ids_matches_name_within_the_org_group():
    wc = FakeWazuh({"acme": [{"id": "5", "name": "WEB-01"}, {"id": "6", "name": "DB-01"}]})
    assert resolve_host_agent_ids(wc, "acme", "web-01") == ["5"]   # case-insensitive
    assert wc.asked == ["acme"]


def test_resolve_host_agent_ids_is_confined_to_the_named_group():
    # WEB-01 exists in beta but we only ever query the acme group -> not reachable
    wc = FakeWazuh({
        "acme": [{"id": "5", "name": "APP-01"}],
        "beta": [{"id": "99", "name": "WEB-01"}],
    })
    assert resolve_host_agent_ids(wc, "acme", "WEB-01") == []
    assert "beta" not in wc.asked


def test_resolve_host_agent_ids_empty_for_missing_inputs():
    wc = FakeWazuh({"acme": [{"id": "5", "name": "WEB-01"}]})
    assert resolve_host_agent_ids(wc, "", "WEB-01") == []
    assert resolve_host_agent_ids(wc, "acme", "") == []
