"""Redis attack buffer — the shared, capped, ephemeral arc store (PRD #594, ADR-0027).

A single append-only buffer with a monotonic ``seq``, bounded BOTH by count
(``MAXLEN``) AND age (entries older than ``MAX_AGE_SECONDS`` are trimmed). It lives
in the Django cache (Redis in production, LocMem under test) — never Postgres, because
Attacks are deliberately throwaway viz data, unlike the durable, auditable HuntEvent.

There is exactly one writer (the Celery-beat producer), so the read-modify-write over
a single cache key needs no locking; SSE connections are readers only. The buffer
doubles as the cold-join backfill: a new client replays it (``since(-1)``) then tails.
"""
import time

from django.core.cache import cache

_BUFFER_KEY = "attackmap:buffer"
_STATS_KEY = "attackmap:stats"

MAXLEN = 500            # count cap
MAX_AGE_SECONDS = 900   # 15-minute age cap


class AttackBuffer:
    def __init__(self, *, maxlen: int = MAXLEN, max_age_seconds: int = MAX_AGE_SECONDS):
        self.maxlen = maxlen
        self.max_age_seconds = max_age_seconds

    # ── internal cache state ────────────────────────────────────────────────
    def _load(self) -> dict:
        return cache.get(_BUFFER_KEY) or {"events": [], "next_seq": 0}

    def _save(self, state: dict) -> None:
        cache.set(_BUFFER_KEY, state, None)

    def _trim(self, events: list, now: float) -> list:
        """Drop entries past the age bound, then past the count bound (oldest first)."""
        cutoff = now - self.max_age_seconds
        events = [e for e in events if e.get("_t", now) >= cutoff]
        if len(events) > self.maxlen:
            events = events[-self.maxlen:]
        return events

    # ── public interface ────────────────────────────────────────────────────
    def append(self, attacks: list, now: float | None = None) -> list:
        """Append attacks, assigning each a monotonic ``seq``. Returns the new seqs."""
        if now is None:
            now = time.time()
        state = self._load()
        events = state["events"]
        seq = state["next_seq"]
        assigned = []
        for attack in attacks:
            entry = dict(attack)
            entry["seq"] = seq
            entry["_t"] = now
            events.append(entry)
            assigned.append(seq)
            seq += 1
        state["events"] = self._trim(events, now)
        state["next_seq"] = seq
        self._save(state)
        return assigned

    def trim(self, now: float | None = None) -> None:
        """Re-apply the age/count bounds without appending (called every tick so the
        buffer stays honest during quiet periods even when nothing new arrives)."""
        if now is None:
            now = time.time()
        state = self._load()
        state["events"] = self._trim(state["events"], now)
        self._save(state)

    def since(self, after_seq: int) -> list:
        """Events with ``seq > after_seq``, oldest first (the SSE tail / backfill)."""
        state = self._load()
        return [e for e in state["events"] if e["seq"] > after_seq]

    def latest_seq(self) -> int:
        state = self._load()
        return state["next_seq"] - 1

    # ── side-panel stats blob (rides alongside the buffer) ────────────────────
    def get_stats(self) -> dict:
        return cache.get(_STATS_KEY) or {}

    def set_stats(self, stats: dict) -> None:
        cache.set(_STATS_KEY, stats, None)
