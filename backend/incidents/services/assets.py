from incidents.models import Asset, IncidentAsset


def link_asset_from_source_ref(incident, source_kind, source_ref):
    """Auto-link a host Asset when an incident originates from a Wazuh source."""
    if source_kind not in ("wazuh_event", "agent_finding"):
        return

    agent = source_ref.get("agent") or {}
    agent_name = source_ref.get("agent_name") or agent.get("name")
    if not agent_name:
        return

    ip_address = source_ref.get("ip_address") or agent.get("ip") or None

    asset, created = Asset.objects.get_or_create(
        organization=incident.organization,
        kind=Asset.KIND_HOST,
        agent_name=agent_name,
        defaults={"name": agent_name, "ip_address": ip_address},
    )

    IncidentAsset.objects.get_or_create(
        incident=incident,
        asset=asset,
        defaults={"added_by": None},
    )
