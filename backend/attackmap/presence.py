"""Presence registry — who is watching the Live Attack Map (PRD #594 slice #598).

Each open map refreshes a short-TTL heartbeat every SSE loop; the producer's first
act each tick is `any_present()` and, with zero viewers, it returns before touching
OpenSearch (ADR-0027 — net backend load is zero while unwatched).

Implemented as a single cache entry mapping ``conn_id -> expiry_epoch``, pruned on
every read so a dropped connection self-heals once its TTL lapses (no stuck count).
There is no central writer, but heartbeats are idempotent and refresh every ~1s while
the TTL is ~15s, so an occasional lost write self-corrects on the next loop.
"""
import time

from django.core.cache import cache

_PRESENCE_KEY = "attackmap:presence"
TTL_SECONDS = 15


def _load(now: float) -> dict:
    entries = cache.get(_PRESENCE_KEY) or {}
    return {cid: exp for cid, exp in entries.items() if exp > now}


def heartbeat(conn_id: str, now: float | None = None) -> None:
    """Refresh (or register) one connection's presence for ``TTL_SECONDS``."""
    if now is None:
        now = time.time()
    entries = _load(now)
    entries[str(conn_id)] = now + TTL_SECONDS
    cache.set(_PRESENCE_KEY, entries, None)


def drop(conn_id: str) -> None:
    """Best-effort immediate removal on a clean SSE disconnect."""
    entries = cache.get(_PRESENCE_KEY) or {}
    entries.pop(str(conn_id), None)
    cache.set(_PRESENCE_KEY, entries, None)


def any_present(now: float | None = None) -> bool:
    """True iff at least one connection has heartbeated within the TTL window."""
    if now is None:
        now = time.time()
    return bool(_load(now))
