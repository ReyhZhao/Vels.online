from incidents.models import Asset, Incident, IncidentAsset


def _wazuh_level_to_severity(level):
    level = int(level or 0)
    if level >= 12:
        return "critical"
    if level >= 9:
        return "high"
    if level >= 6:
        return "medium"
    return "low"


def _cvss_to_severity(score):
    if score is None:
        return "medium"
    score = float(score)
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def build_promote_payload(source_kind, source_ref):
    if source_kind == "wazuh_event":
        rule_desc = source_ref.get("rule_description", "Unknown rule")
        agent_name = source_ref.get("agent_name", "unknown agent")
        title = f"Wazuh alert on {agent_name}: {rule_desc}"
        description = f"Wazuh alert triggered:\n  Rule: {rule_desc}\n  Agent: {agent_name}"
        severity = _wazuh_level_to_severity(source_ref.get("level"))
    elif source_kind == "vulnerability":
        cve_id = source_ref.get("cve_id", "")
        desc_text = source_ref.get("description", "")
        title = f"{cve_id}: {desc_text[:80]}" if desc_text else cve_id
        description = desc_text or ""
        severity = _cvss_to_severity(source_ref.get("cvss_score"))
    elif source_kind == "agent_finding":
        agent_name = source_ref.get("agent_name", "unknown agent")
        cve_id = source_ref.get("cve_id", "")
        title = (
            f"Agent finding on {agent_name}: {cve_id}"
            if cve_id
            else f"Agent finding on {agent_name}"
        )
        description = (
            f"Vulnerability {cve_id} detected on agent {agent_name}."
            if cve_id
            else f"Finding on agent {agent_name}."
        )
        severity = _cvss_to_severity(source_ref.get("cvss_score"))
    else:
        title = ""
        description = ""
        severity = "medium"

    return {
        "title": title,
        "description": description,
        "severity": severity,
        "source_kind": source_kind,
        "source_ref": source_ref,
    }


def link_source_assets(incident, org):
    """Create IncidentAsset entries for agents referenced in the incident's source_ref."""
    source_ref = incident.source_ref or {}
    source_kind = incident.source_kind

    agent_names = []
    if source_kind in ("wazuh_event", "agent_finding"):
        name = source_ref.get("agent_name")
        if name:
            agent_names = [name]
    elif source_kind == "vulnerability":
        raw = source_ref.get("affected_agents", [])
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, str):
                    agent_names.append(entry)
                elif isinstance(entry, dict) and entry.get("agent_name"):
                    agent_names.append(entry["agent_name"])

    agent_names = [n for n in agent_names if n]
    if not agent_names:
        return

    assets = Asset.objects.filter(
        organization=org,
        kind=Asset.KIND_HOST,
        agent_name__in=agent_names,
    )
    for asset in assets:
        IncidentAsset.objects.get_or_create(incident=incident, asset=asset, defaults={"added_by": None})


def find_open_incidents(source_kind, source_ref):
    qs = Incident.objects.filter(source_kind=source_kind).exclude(state="closed")
    for key, value in (source_ref or {}).items():
        qs = qs.filter(**{f"source_ref__{key}": value})
    return list(
        qs.select_related("organization", "subject", "assignee", "created_by").order_by("-created_at")
    )
