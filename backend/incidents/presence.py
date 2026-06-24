"""Incident Presence registry (PRD #605, ADR-0028).

A per-incident ephemeral roster held in the cache (Redis) — never the ORM, never
the IncidentEvent timeline. The registry is both the source of truth and the thing
streamed over SSE: there is no producer, no shared buffer, no Celery beat.

Each entry is keyed ``(incident, actor)`` (not per-connection — tabs collapse,
last-write-wins per actor) and carries ``{activity, target, expiry, identity}``.
Heartbeats refresh *expiry only* (preserving a declared ``working``/``editing``
activity) on a ~15s TTL, so a dead tab self-heals.

Editing an *existing* comment additionally rides a soft lock on the same record:
the first editor holds it; the lock self-releases on TTL (dead tab) or after a
~5-minute idle window since the last keystroke (``refresh_comment_lock``).

Everything here **fails open / degrades invisible**: any cache error is swallowed,
reads return an empty roster, writes no-op, and lock acquisition is treated as
granted — a presence outage must never break the incident page or block editing.
"""
import logging
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)

TTL_SECONDS = 15
# Idle auto-release window for a held comment-edit lock, refreshed on every
# keystroke. A walked-away-but-open editor cannot deadlock the comment.
LOCK_IDLE_SECONDS = 300

ACTIVITY_VIEWING = "viewing"
ACTIVITY_WORKING = "working"
ACTIVITY_EDITING = "editing"
VALID_ACTIVITIES = {ACTIVITY_VIEWING, ACTIVITY_WORKING, ACTIVITY_EDITING}

ACTOR_HUMAN = "human"
ACTOR_AI = "ai"


def _key(incident_id) -> str:
    return f"incident:presence:{incident_id}"


def human_actor_key(user_id) -> str:
    return f"user:{user_id}"


def _now(now: float | None) -> float:
    return time.time() if now is None else now


def _prune(entries: dict, now: float) -> dict:
    """Drop expired actors and downgrade idle-expired comment-edit locks.

    A live actor whose lock idle-window lapsed stays present but reverts to
    ``viewing`` with no target — that is the lock's idle auto-release.
    """
    out = {}
    for actor_key, rec in entries.items():
        if not isinstance(rec, dict) or rec.get("expiry", 0) <= now:
            continue
        if (
            rec.get("activity") == ACTIVITY_EDITING
            and rec.get("target") is not None
            and rec.get("lock_idle_expiry", 0) <= now
        ):
            rec = {**rec, "activity": ACTIVITY_VIEWING, "target": None}
            rec.pop("lock_idle_expiry", None)
        out[actor_key] = rec
    return out


def _load_for(incident_id, now: float) -> dict:
    entries = cache.get(_key(incident_id)) or {}
    return _prune(entries, now)


def _public(actor_key: str, rec: dict) -> dict:
    return {
        "actor_key": actor_key,
        "actor_kind": rec.get("actor_kind", ACTOR_HUMAN),
        "actor_id": rec.get("actor_id"),
        "display_name": rec.get("display_name", ""),
        "activity": rec.get("activity", ACTIVITY_VIEWING),
        "target": rec.get("target"),
        "run_by": rec.get("run_by"),
    }


def roster(incident_id, now: float | None = None) -> list[dict]:
    """Return the current roster as a list of public dicts. Fail-open to []."""
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
        return [_public(k, rec) for k, rec in sorted(entries.items())]
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("presence.roster failed for %s: %s", incident_id, exc)
        return []


def heartbeat(incident_id, actor_key, *, display_name="", actor_id=None,
              actor_kind=ACTOR_HUMAN, run_by=None, now: float | None = None) -> None:
    """Register (as ``viewing``) or refresh-expiry-only an actor. Never clobbers a
    declared ``working``/``editing`` activity. Fail-open no-op on cache error."""
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
        rec = entries.get(actor_key)
        if rec is None:
            rec = {
                "activity": ACTIVITY_VIEWING,
                "target": None,
                "actor_kind": actor_kind,
                "actor_id": actor_id,
                "display_name": display_name,
                "run_by": run_by,
            }
        # Refresh expiry only; preserve activity/target/lock and keep identity fresh.
        rec["expiry"] = now + TTL_SECONDS
        if display_name:
            rec["display_name"] = display_name
        if actor_id is not None:
            rec["actor_id"] = actor_id
        rec["actor_kind"] = actor_kind
        if run_by is not None:
            rec["run_by"] = run_by
        entries[actor_key] = rec
        cache.set(_key(incident_id), entries, None)
    except Exception as exc:
        logger.debug("presence.heartbeat failed for %s/%s: %s", incident_id, actor_key, exc)


def set_activity(incident_id, actor_key, activity, target=None, *, display_name="",
                 actor_id=None, actor_kind=ACTOR_HUMAN, run_by=None,
                 now: float | None = None) -> None:
    """Set a declared activity for an actor, refreshing expiry. Fail-open no-op.

    Use for advisory facets (``working`` a task; ``editing`` a *new* comment with
    no target). For locking an existing comment use ``acquire_comment_lock``.
    """
    if activity not in VALID_ACTIVITIES:
        return
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
        rec = entries.get(actor_key) or {
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "display_name": display_name,
            "run_by": run_by,
        }
        rec["activity"] = activity
        rec["target"] = target
        rec["expiry"] = now + TTL_SECONDS
        rec.pop("lock_idle_expiry", None)
        if display_name:
            rec["display_name"] = display_name
        if actor_id is not None:
            rec["actor_id"] = actor_id
        rec["actor_kind"] = actor_kind
        if run_by is not None:
            rec["run_by"] = run_by
        entries[actor_key] = rec
        cache.set(_key(incident_id), entries, None)
    except Exception as exc:
        logger.debug("presence.set_activity failed for %s/%s: %s", incident_id, actor_key, exc)


def comment_lock_holder(incident_id, comment_id, exclude_actor=None,
                        now: float | None = None) -> dict | None:
    """Return the public record of a live lock holder on ``comment_id``, else None."""
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
    except Exception:
        return None
    for actor_key, rec in entries.items():
        if actor_key == exclude_actor:
            continue
        if (
            rec.get("activity") == ACTIVITY_EDITING
            and rec.get("target") == comment_id
            and rec.get("lock_idle_expiry", 0) > now
        ):
            return _public(actor_key, rec)
    return None


def acquire_comment_lock(incident_id, actor_key, comment_id, *, display_name="",
                         actor_id=None, now: float | None = None) -> tuple[bool, dict | None]:
    """Acquire (or refresh, if already mine) the soft edit lock on an existing comment.

    Returns ``(granted, holder)``. ``granted`` is True when this actor now holds the
    lock; ``holder`` is the *other* holder's public record when denied. **Fails open**:
    on any cache error returns ``(True, None)`` so editing is never blocked.
    """
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
        for other_key, rec in entries.items():
            if other_key == actor_key:
                continue
            if (
                rec.get("activity") == ACTIVITY_EDITING
                and rec.get("target") == comment_id
                and rec.get("lock_idle_expiry", 0) > now
            ):
                return False, _public(other_key, rec)

        rec = entries.get(actor_key) or {
            "actor_kind": ACTOR_HUMAN,
            "actor_id": actor_id,
            "display_name": display_name,
        }
        rec["activity"] = ACTIVITY_EDITING
        rec["target"] = comment_id
        rec["expiry"] = now + TTL_SECONDS
        rec["lock_idle_expiry"] = now + LOCK_IDLE_SECONDS
        if display_name:
            rec["display_name"] = display_name
        if actor_id is not None:
            rec["actor_id"] = actor_id
        rec.setdefault("actor_kind", ACTOR_HUMAN)
        entries[actor_key] = rec
        cache.set(_key(incident_id), entries, None)
        return True, None
    except Exception as exc:
        logger.debug("presence.acquire_comment_lock fail-open for %s/%s: %s",
                     incident_id, actor_key, exc)
        return True, None


def refresh_comment_lock(incident_id, actor_key, comment_id,
                         now: float | None = None) -> None:
    """Reset the idle window on a held lock (called on each keystroke). Fail-open."""
    now = _now(now)
    try:
        entries = _load_for(incident_id, now)
        rec = entries.get(actor_key)
        if not rec or rec.get("target") != comment_id:
            return
        rec["activity"] = ACTIVITY_EDITING
        rec["expiry"] = now + TTL_SECONDS
        rec["lock_idle_expiry"] = now + LOCK_IDLE_SECONDS
        entries[actor_key] = rec
        cache.set(_key(incident_id), entries, None)
    except Exception as exc:
        logger.debug("presence.refresh_comment_lock failed for %s/%s: %s",
                     incident_id, actor_key, exc)


def drop(incident_id, actor_key) -> None:
    """Best-effort immediate removal on clean disconnect / blur. Fail-open no-op."""
    try:
        entries = cache.get(_key(incident_id)) or {}
        if actor_key in entries:
            entries.pop(actor_key, None)
            cache.set(_key(incident_id), entries, None)
    except Exception as exc:
        logger.debug("presence.drop failed for %s/%s: %s", incident_id, actor_key, exc)
