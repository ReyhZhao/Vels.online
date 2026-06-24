from incidents.models import Asset, IncidentAsset


def link_asset_from_source_ref(incident, source_kind, source_ref):
    """Auto-link a host Asset when an incident originates from a Wazuh source.

    Handles streaming Wazuh sources (wazuh_event/agent_finding) and scheduled-search
    Alerts (#601): a scheduled_search Alert's source_ref is the raw Wazuh `_source` doc,
    whose host identity lives at `agent.name` (and `agent.ip`), the same shape this reads.
    """
    if source_kind not in ("wazuh_event", "agent_finding", "scheduled_search"):
        return

    if not isinstance(source_ref, dict):
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

    from incidents.services.contacts import auto_link_contacts_for_asset
    auto_link_contacts_for_asset(incident, asset)
