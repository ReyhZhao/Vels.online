"""Snapshot producer — the single shared OpenSearch tick (PRD #594, ADR-0027).

Called by the Celery-beat task every ~10s. The first act is a presence check: with
zero viewers it returns *before* any OpenSearch call, so the feature costs nothing
while unwatched. Otherwise it runs ONE query (hits + aggregations), projects new hits
to Attacks (geo-resolver + destination resolver), appends them to the shared buffer,
and writes the side-panel stats blob. Net OpenSearch load is bounded to
``[0, ~6 queries/min]`` for the whole deployment, independent of audience.

Dedup: a bounded set of recently-seen document ids means the same event is appended
as an arc once, not on every overlapping window. After an idle gap the window's ids
are unseen, so the first tick repaints recent history rather than an empty world.
"""
import logging
import time

from django.core.cache import cache

from . import presence
from .buffer import AttackBuffer
from .config import get_severity_floor
from .destination import get_destination_resolver
from .projection import RESERVED, attack_type_label, project_attack

logger = logging.getLogger(__name__)

_SEEN_IDS_KEY = "attackmap:seen_ids"
_SEEN_IDS_CAP = 2000
WINDOW_MINUTES = 15
HITS_SIZE = 300


def _load_seen_ids() -> list:
    return cache.get(_SEEN_IDS_KEY) or []


def _save_seen_ids(seen: list) -> None:
    cache.set(_SEEN_IDS_KEY, seen[-_SEEN_IDS_CAP:], None)


def _build_stats(snapshot: dict) -> dict:
    """Side-panel aggregates from the single query's aggregations (fixed window)."""
    aggs = snapshot.get("aggregations", {})

    # Top source countries: merge Wazuh-GeoIP and FortiGate (srccountry) buckets,
    # dropping the "Reserved" internal sentinel.
    country_counts: dict = {}
    for key in ("by_geo_country", "by_src_country"):
        for bucket in aggs.get(key, {}).get("buckets", []):
            name = bucket.get("key")
            if not name or name == RESERVED:
                continue
            country_counts[name] = country_counts.get(name, 0) + bucket.get("doc_count", 0)
    top_countries = sorted(country_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]

    # Top attack types: rule.groups terms, cleaned via the same label rules as arcs.
    type_counts: dict = {}
    for bucket in aggs.get("by_attack_type", {}).get("buckets", []):
        label = attack_type_label({"groups": [bucket.get("key")]})
        if not label:
            continue
        type_counts[label] = type_counts.get(label, 0) + bucket.get("doc_count", 0)
    top_types = sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]

    total = snapshot.get("total", 0)
    window = snapshot.get("window_minutes", WINDOW_MINUTES) or WINDOW_MINUTES
    return {
        "top_countries": [list(c) for c in top_countries],
        "top_attack_types": [list(t) for t in top_types],
        "per_minute": round(total / window),
        "total": total,
        "window_minutes": window,
        "updated_at": time.time(),
    }


def run_snapshot_tick(os_client, wazuh_client, *, floor: int | None = None, now: float | None = None) -> dict:
    """One producer tick. Returns a small summary dict (also handy for tests/logs)."""
    if now is None:
        now = time.time()

    # ADR-0027: zero OpenSearch load when nobody is watching.
    if not presence.any_present(now=now):
        return {"skipped": True, "reason": "no_presence"}

    if floor is None:
        floor = get_severity_floor()

    snapshot = os_client.get_attack_snapshot(floor=floor, window_minutes=WINDOW_MINUTES, size=HITS_SIZE)
    resolver = get_destination_resolver(wazuh_client)
    buf = AttackBuffer()

    seen = _load_seen_ids()
    seen_set = set(seen)
    new_attacks = []
    # Oldest-first so seq order matches chronological order.
    for hit in reversed(snapshot.get("hits", [])):
        doc_id = hit.get("_id")
        if doc_id and doc_id in seen_set:
            continue
        if doc_id:
            seen.append(doc_id)
            seen_set.add(doc_id)
        attack = project_attack(hit.get("_source", {}), floor)
        if attack is None:
            continue
        lat, lng, label = resolver.resolve(attack.pop("agent_id", ""))
        attack["dst_org_label"] = label
        attack["dst_lat"] = lat
        attack["dst_lng"] = lng
        new_attacks.append(attack)

    assigned = buf.append(new_attacks, now=now)
    buf.trim(now=now)  # keep the buffer honest during quiet periods (slice #598)
    buf.set_stats(_build_stats(snapshot))
    _save_seen_ids(seen)

    return {"skipped": False, "appended": len(assigned), "floor": floor}
