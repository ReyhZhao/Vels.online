"""Live Attack Map configuration (PRD #594 slice #600).

A single global severity floor feeds the producer's query. Default 3 (deliberately
low for arc density while the map is young), intended to be raised toward 7 later.
It is a *config flip, not a redeploy*: a runtime cache override takes precedence over
the ``ATTACK_MAP_SEVERITY_FLOOR`` setting, so an operator can change it live.

Per-viewer *server-side* floors are explicitly out of scope (ADR-0027 — they would
break the shared-buffer O(1) guarantee). Viewers filter HIGHER purely client-side.
"""
from django.conf import settings
from django.core.cache import cache

_FLOOR_OVERRIDE_KEY = "attackmap:severity_floor"
DEFAULT_FLOOR = 3


def get_severity_floor() -> int:
    """The active producer severity floor: live override → setting → default."""
    override = cache.get(_FLOOR_OVERRIDE_KEY)
    if override is not None:
        return int(override)
    return int(getattr(settings, "ATTACK_MAP_SEVERITY_FLOOR", DEFAULT_FLOOR))


def set_severity_floor(level: int) -> None:
    """Flip the global floor live (no redeploy). Clamped to the valid rule.level band."""
    cache.set(_FLOOR_OVERRIDE_KEY, max(0, min(15, int(level))), None)
