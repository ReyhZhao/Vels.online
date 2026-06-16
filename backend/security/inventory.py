"""IT Hygiene Inventory query core (ADR-0022).

Pure query-building and projection over Wazuh's ``wazuh-states-inventory-*`` OpenSearch
state indices — installed software, running processes, and services. No client or Django
dependency: callers pass agent ids + args, feed ``build_inventory_query``'s body to
``OpenSearchClient._search``, then parse the hits with ``project_hits``. Kept pure so the
index patterns, the ``agent.id`` scoping, and the per-kind projections are unit-testable
without touching infrastructure.

The indices use ECS-style top-level objects (``agent.*``, ``host.*``, ``process.*``,
``service.*``, ``package.*``), not the old ``data.*`` syscollector shape. Field paths
below are verified against the 4.14.1 index mappings.
"""

INVENTORY_KINDS = ("software", "service", "process")

# kind -> index pattern. The trailing "-*" tolerates the per-node suffix
# (the live indices are e.g. ``wazuh-states-inventory-packages-wazuh``).
_INDEX = {
    "software": "wazuh-states-inventory-packages-*",
    "service": "wazuh-states-inventory-services-*",
    "process": "wazuh-states-inventory-processes-*",
}

# kind -> the tight set of ECS field paths projected back to the model (bounds token cost).
_PROJECTION = {
    "software": ["package.name", "package.version", "package.vendor", "package.architecture"],
    "service": ["service.name", "service.state", "service.sub_state",
                "service.start_type", "service.enabled", "service.description"],
    "process": ["process.name", "process.pid", "process.executable",
                "process.args", "process.user.name"],
}

# kind -> the field a `name` query matches against.
_NAME_FIELD = {
    "software": "package.name",
    "service": "service.name",
    "process": "process.name",
}

DEFAULT_SIZE = 50


def is_valid_kind(kind) -> bool:
    return kind in _INDEX


def index_for(kind):
    return _INDEX.get(kind)


def name_field_for(kind):
    return _NAME_FIELD.get(kind)


def _dig(source: dict, path: str):
    """Read a dotted path out of a nested _source dict, tolerating missing keys."""
    cur = source
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def build_inventory_query(kind, agent_ids, name=None, size=DEFAULT_SIZE) -> dict:
    """Build the OpenSearch body for an inventory query, scoped to ``agent_ids``.

    The ``agent.id`` terms filter is always filter[0] (the tenant-isolation boundary).
    When ``name`` is given, adds a case-insensitive substring match on the kind's name
    field. Projects only the allowlisted ``_source`` fields plus agent identity.
    """
    filters = [{"terms": {"agent.id": [str(a) for a in agent_ids]}}]
    if name:
        filters.append({"wildcard": {_NAME_FIELD[kind]: {
            "value": f"*{name}*", "case_insensitive": True}}})
    return {
        "query": {"bool": {"filter": filters}},
        "_source": _PROJECTION[kind] + ["agent.id", "agent.name", "host.name"],
        "size": size,
        "track_total_hits": True,
    }


def project_hit(kind, hit: dict) -> dict:
    """Flatten one OpenSearch hit into a compact row: agent identity + the kind's fields.

    The kind prefix (``package.``/``service.``/``process.``) is stripped from each key,
    so a software row reads ``{name, version, vendor, architecture}`` and a process row
    ``{name, pid, executable, args, user.name}`` — no cross-field collisions within a kind.
    """
    source = hit.get("_source", {}) or {}
    agent = source.get("agent", {}) or {}
    row = {"agent_id": agent.get("id"), "agent_name": agent.get("name")}
    prefix = _PROJECTION[kind][0].split(".")[0] + "."
    for path in _PROJECTION[kind]:
        key = path[len(prefix):] if path.startswith(prefix) else path
        row[key] = _dig(source, path)
    return row


def project_hits(kind, hits) -> list:
    return [project_hit(kind, h) for h in hits]


def resolve_host_agent_ids(wazuh_client, wazuh_group, host_name) -> list:
    """Resolve a host name to its Wazuh agent id(s) *within one org's group*.

    Returns the agent ids whose name matches ``host_name`` (case-insensitive), restricted
    to ``wazuh_group`` — so a same-named host in another org is never reachable. Used by
    the Incident Assistant's host-inventory tool to keep the query inside the incident's
    organisation (ADR-0022).
    """
    if not wazuh_group or not host_name:
        return []
    agents = wazuh_client.get_agents(wazuh_group) or []
    target = host_name.strip().lower()
    return [str(a["id"]) for a in agents
            if a.get("id") and (a.get("name") or "").strip().lower() == target]
