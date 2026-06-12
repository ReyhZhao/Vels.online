"""Resolve a Hunt's org scope into per-tenant agent-id sets (ADR-0015).

The tenant-isolation invariant lives here: a Hunt's scope is expanded to a list of
OrgScope, one per organisation, each carrying *only that org's* Wazuh agent ids. Every
lens iterates this list and queries one org at a time, so a cross-org hunt fans out
per tenant and a single query never mixes agents from two orgs.
"""
import logging
from dataclasses import dataclass, field
from typing import List

from security.models import Organization

logger = logging.getLogger(__name__)


@dataclass
class OrgScope:
    org_id: int
    org_name: str
    wazuh_group: str
    agent_ids: List[str] = field(default_factory=list)


def resolve_scope(hunt, wazuh_client=None) -> List[OrgScope]:
    """Expand hunt.scope into per-org agent-id sets.

    `wazuh_client` is injectable so tests never hit Wazuh. An org whose agents can't
    be fetched yields an empty agent_ids list (it is skipped by lenses, never widened).
    """
    from security.wazuh import WazuhClient

    wc = wazuh_client or WazuhClient()

    if hunt.scope_all_orgs:
        orgs = list(Organization.objects.all())
    else:
        orgs = list(hunt.scope_orgs.all())

    out: List[OrgScope] = []
    for org in orgs:
        agent_ids: List[str] = []
        try:
            agents = wc.get_agents(org.wazuh_group)
            agent_ids = [str(a["id"]) for a in agents if a.get("id")]
        except Exception as exc:  # one org failing must not abort the whole hunt
            logger.warning("resolve_scope: could not fetch agents for org %s: %s", org.id, exc)
        out.append(OrgScope(
            org_id=org.id,
            org_name=org.name,
            wazuh_group=org.wazuh_group,
            agent_ids=agent_ids,
        ))
    return out
