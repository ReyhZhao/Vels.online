import json

import yaml


class UnresolvableVarError(Exception):
    def __init__(self, var_name: str, source: str):
        self.var_name = var_name
        self.source = source
        super().__init__(f"Mapping for '{var_name}' (source: {source}) resolved to no values.")


_SCALAR_SOURCES = {"incident.title", "incident.severity"}


def resolve_incident_vars(mappings_yaml: str, incident) -> dict[str, str]:
    mappings = yaml.safe_load(mappings_yaml)
    if not isinstance(mappings, list):
        raise ValueError("incident_var_mappings must be a YAML list")

    result = {}
    for entry in mappings:
        var = entry["var"]
        source = entry["source"]
        fmt = entry.get("format", "colon_separated")
        values = _resolve_source(source, incident)
        if not values:
            raise UnresolvableVarError(var, source)
        if source in _SCALAR_SOURCES:
            result[var] = values[0]
        else:
            result[var] = _serialize(values, fmt)

    return result


def _resolve_source(source: str, incident) -> list[str]:
    if source == "assets.agent_name":
        return [a.agent_name for a in incident.assets.all() if a.kind == "host" and a.agent_name]
    if source == "assets.ip_address":
        return [str(a.ip_address) for a in incident.assets.all() if a.kind == "host" and a.ip_address]
    if source == "iocs.ip":
        return [ioc.value for ioc in incident.iocs.all() if ioc.kind == "ip"]
    if source == "iocs.domain":
        return [ioc.value for ioc in incident.iocs.all() if ioc.kind == "domain"]
    if source == "iocs.url":
        return [ioc.value for ioc in incident.iocs.all() if ioc.kind == "url"]
    if source == "incident.title":
        return [incident.title] if incident.title else []
    if source == "incident.severity":
        return [incident.severity] if incident.severity else []
    raise ValueError(f"Unknown source: {source}")


def _serialize(values: list[str], fmt: str) -> str:
    if fmt == "colon_separated":
        return ":".join(values)
    if fmt == "comma_separated":
        return ",".join(values)
    if fmt == "json_array":
        return json.dumps(values)
    raise ValueError(f"Unknown format: {fmt}")
