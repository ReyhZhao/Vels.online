"""Destination resolver — agent.id → (lat, lng, org_label) (PRD #594 slice #597).

Splits cleanly in two:

* `DestinationResolver` — a **pure** resolver over an injected reverse agent→org map
  and a home point. No I/O; exhaustively unit-tested.
* `build_reverse_map` / `get_destination_resolver` — the I/O + caching layer that
  builds the reverse map from each org's Wazuh group membership.

`agent.id == "000"` is the shared perimeter (ADR-0017) → the Infrastructure org's
home point. An unknown agent, or an org with no location set, also falls back to the
home point (never a (0, 0) arc).
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

INFRA_AGENT_ID = "000"
_REVERSE_MAP_CACHE_KEY = "attackmap:reverse_agent_org_map"
_REVERSE_MAP_TTL = 300  # seconds


class DestinationResolver:
    """Pure: resolve an agent id to where its arc should land.

    ``reverse_map`` maps ``agent_id -> (lat, lng, org_label)`` where lat/lng may be
    ``None`` (org has no location). ``home`` is the ``(lat, lng, label)`` perimeter
    point used for agent ``"000"``, unknown agents, and located-less orgs.
    """

    def __init__(self, reverse_map: dict, home: tuple):
        self._map = reverse_map or {}
        self._home = home

    def resolve(self, agent_id) -> tuple:
        agent_id = str(agent_id or "")
        if agent_id == INFRA_AGENT_ID:
            return self._home

        entry = self._map.get(agent_id)
        if entry is None:
            return self._home

        lat, lng, label = entry
        if lat is None or lng is None:
            # Known org but no coordinates → land on the home point under its own label.
            return (self._home[0], self._home[1], label)
        return (lat, lng, label)


def _home_point():
    """The Infrastructure org's coordinates (ADR-0017), or a sane default."""
    from security.models import Organization, INFRASTRUCTURE_ORG_NAME

    infra = Organization.objects.filter(is_infrastructure=True).first()
    if infra and infra.latitude is not None and infra.longitude is not None:
        return (infra.latitude, infra.longitude, infra.name)
    # No Infrastructure coordinate configured yet: a neutral perimeter anchor.
    return (52.37, 4.9, INFRASTRUCTURE_ORG_NAME)


def build_reverse_map(wazuh_client) -> dict:
    """Build ``agent_id -> (lat, lng, org_label)`` from every tenant org's group.

    One Wazuh API call per org. The Infrastructure org is excluded (its agent is the
    fixed ``"000"`` perimeter, resolved directly to the home point).
    """
    from security.models import Organization

    reverse: dict = {}
    for org in Organization.objects.tenants():
        if not org.wazuh_group:
            continue
        try:
            agents = wazuh_client.get_agents(org.wazuh_group) or []
        except Exception as exc:  # a flaky Wazuh API must not kill the whole snapshot
            logger.warning("attackmap: failed to list agents for org %s: %s", org.slug, exc)
            continue
        for agent in agents:
            agent_id = str(agent.get("id") or "")
            if agent_id:
                reverse[agent_id] = (org.latitude, org.longitude, org.name)
    return reverse


def get_destination_resolver(wazuh_client) -> DestinationResolver:
    """A `DestinationResolver` backed by a cached reverse map (rebuilt every ~5 min)."""
    reverse = cache.get(_REVERSE_MAP_CACHE_KEY)
    if reverse is None:
        reverse = build_reverse_map(wazuh_client)
        cache.set(_REVERSE_MAP_CACHE_KEY, reverse, _REVERSE_MAP_TTL)
    return DestinationResolver(reverse, _home_point())
