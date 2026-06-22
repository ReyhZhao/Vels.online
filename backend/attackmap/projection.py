"""Attack projection — the pure doc→Attack geo-resolver (PRD #594, ADR-0027).

Input: one raw Wazuh `_source` document. Output: an Attack dict (the *source* half
of a map arc) or ``None`` if the document is not a v1 Attack. No I/O — every geo /
severity edge case is exercised by `backend/tests/test_attackmap_projection.py`.

The destination half (which org the arc lands on) is resolved separately by
`destination.py`; the producer (`producer.py`) joins the two and the buffer assigns
the monotonic ``seq``. Keeping this a pure function is the crown-jewel testability
decision of the feature.
"""
from .centroids import COUNTRY_CENTROIDS

# The literal firewall sentinel that means "internal endpoint" — never a country.
# On the source it marks internal-origin traffic → excluded from v1 (inbound only;
# the egress axis is deferred). On the destination it is the normal inbound case and
# is ignored (destination never comes from the doc's geo).
RESERVED = "Reserved"

# Severity → arc colour, reusing the critical/high/medium/low rule.level bands from
# security/opensearch.py (_SEVERITY_LEVEL_RANGES). The floor can sit as low as 3, so
# low-band events are coloured too rather than dropped.
_COLOR_CRITICAL = "#ef4444"  # red-500   — level >= 12
_COLOR_HIGH = "#f97316"      # orange-500 — 8..11
_COLOR_MEDIUM = "#f59e0b"    # amber-500  — 4..7
_COLOR_LOW = "#facc15"       # yellow-400 — < 4

# rule.groups tokens that describe *how* it fired rather than *what* the attack is;
# the projection prefers a more specific group for the attack-type label.
_GENERIC_GROUPS = {"attack", "ids", "syslog", "wazuh", "pci_dss", "gdpr", "hipaa", "nist_800_53", "tsc", "gpg13"}


def severity_color(level: int) -> str:
    if level >= 12:
        return _COLOR_CRITICAL
    if level >= 8:
        return _COLOR_HIGH
    if level >= 4:
        return _COLOR_MEDIUM
    return _COLOR_LOW


def attack_type_label(rule: dict) -> str:
    """A human-ish attack-type label from rule.groups, falling back to rule.description."""
    groups = rule.get("groups") or []
    for group in groups:
        if group and group not in _GENERIC_GROUPS:
            return group.replace("_", " ")
    if groups:
        return str(groups[0]).replace("_", " ")
    description = rule.get("description") or "Attack"
    return str(description)[:80]


def _parse_location(location) -> tuple | None:
    """Normalise a Wazuh GeoLocation.location geo_point to (lat, lng).

    Wazuh emits it as ``{"lat": .., "lon": ..}``; tolerate the GeoJSON ``[lon, lat]``
    array form too. Returns ``None`` for anything unparseable.
    """
    if isinstance(location, dict):
        lat = location.get("lat")
        lng = location.get("lon", location.get("lng"))
        if lat is not None and lng is not None:
            return (float(lat), float(lng))
        return None
    if isinstance(location, (list, tuple)) and len(location) == 2:
        # GeoJSON order is [lon, lat].
        return (float(location[1]), float(location[0]))
    return None


def _resolve_source(doc: dict, centroids: dict) -> tuple | None:
    """Resolve the source country + coordinates per the v1 priority rules.

    (1) ``GeoLocation.country_name`` set → exact ``GeoLocation.location`` if present,
        else the country centroid; (2) else ``data.srccountry`` present and not
        ``"Reserved"`` → country centroid; (3) else → ``None``.
    """
    geo = doc.get("GeoLocation") or {}
    country = geo.get("country_name")
    if country:
        loc = _parse_location(geo.get("location"))
        if loc is not None:
            return (country, loc[0], loc[1])
        centroid = centroids.get(country)
        if centroid is not None:
            return (country, centroid[0], centroid[1])
        return None

    data = doc.get("data") or {}
    srccountry = data.get("srccountry")
    if srccountry and srccountry != RESERVED:
        centroid = centroids.get(srccountry)
        if centroid is not None:
            return (srccountry, centroid[0], centroid[1])
        return None

    return None


def project_attack(doc: dict, floor: int, centroids: dict | None = None) -> dict | None:
    """Project one raw Wazuh document to an Attack (source half), or ``None``.

    Drops docs below ``floor`` and docs whose source does not resolve to a real
    foreign country. The returned dict carries no ``seq`` (assigned by the buffer)
    and no destination (joined by the producer via `destination.py`).
    """
    if centroids is None:
        centroids = COUNTRY_CENTROIDS

    rule = doc.get("rule") or {}
    try:
        level = int(rule.get("level"))
    except (TypeError, ValueError):
        return None
    if level < floor:
        return None

    source = _resolve_source(doc, centroids)
    if source is None:
        return None
    src_country, src_lat, src_lng = source

    return {
        "ts": doc.get("@timestamp") or doc.get("timestamp"),
        "level": level,
        "color": severity_color(level),
        "attack_type": attack_type_label(rule),
        "src_country": src_country,
        "src_lat": src_lat,
        "src_lng": src_lng,
        "agent_id": str((doc.get("agent") or {}).get("id") or ""),
    }
