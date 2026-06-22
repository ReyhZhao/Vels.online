"""Attack projection (geo-resolver) — the crown-jewel pure-module suite (PRD #594 #596).

Table-driven over crafted Wazuh docs. No I/O, no DB.
"""
import pytest

from attackmap.projection import (
    attack_type_label,
    project_attack,
    severity_color,
)

FLOOR = 3
CENTROIDS = {"China": (35.0, 103.0), "Brazil": (-10.0, -52.0)}


def doc(**kw):
    """Build a minimal Wazuh _source with sensible defaults."""
    base = {"rule": {"level": 7, "groups": ["web", "attack"]}, "agent": {"id": "001"}, "@timestamp": "2026-06-22T10:00:00Z"}
    base.update(kw)
    return base


def test_precise_geolocation_point_used_when_present():
    d = doc(GeoLocation={"country_name": "China", "location": {"lat": 39.9, "lon": 116.4}})
    attack = project_attack(d, FLOOR, CENTROIDS)
    assert attack["src_country"] == "China"
    assert attack["src_lat"] == 39.9 and attack["src_lng"] == 116.4


def test_centroid_fallback_for_fortigate_only_event():
    # No Wazuh GeoLocation; only FortiGate data.srccountry → country centroid.
    d = doc(data={"srccountry": "Brazil"})
    d.pop("GeoLocation", None)
    attack = project_attack(d, FLOOR, CENTROIDS)
    assert attack["src_country"] == "Brazil"
    assert (attack["src_lat"], attack["src_lng"]) == (-10.0, -52.0)


def test_reserved_source_is_excluded():
    d = doc(data={"srccountry": "Reserved"})
    assert project_attack(d, FLOOR, CENTROIDS) is None


def test_below_floor_is_dropped():
    d = doc(rule={"level": 2, "groups": ["web"]}, GeoLocation={"country_name": "China", "location": {"lat": 1, "lon": 2}})
    assert project_attack(d, FLOOR, CENTROIDS) is None


def test_no_geo_at_all_is_none():
    d = doc()
    d.pop("GeoLocation", None)
    assert project_attack(d, FLOOR, CENTROIDS) is None


def test_unknown_centroid_country_is_dropped():
    d = doc(data={"srccountry": "Atlantis"})
    d.pop("GeoLocation", None)
    assert project_attack(d, FLOOR, CENTROIDS) is None


def test_geolocation_takes_priority_over_srccountry():
    d = doc(
        GeoLocation={"country_name": "China", "location": {"lat": 39.9, "lon": 116.4}},
        data={"srccountry": "Brazil"},
    )
    attack = project_attack(d, FLOOR, CENTROIDS)
    assert attack["src_country"] == "China"


def test_attack_type_label_prefers_specific_group():
    assert attack_type_label({"groups": ["attack", "sshd_brute_force"]}) == "sshd brute force"


def test_attack_type_label_falls_back_to_description():
    assert attack_type_label({"groups": [], "description": "Multiple failed logins"}) == "Multiple failed logins"


@pytest.mark.parametrize(
    "level,color",
    [(13, "#ef4444"), (12, "#ef4444"), (9, "#f97316"), (5, "#f59e0b"), (3, "#facc15")],
)
def test_severity_color_bands(level, color):
    assert severity_color(level) == color


def test_attack_carries_type_and_color():
    d = doc(rule={"level": 12, "groups": ["sql_injection"]},
            GeoLocation={"country_name": "China", "location": {"lat": 1, "lon": 2}})
    attack = project_attack(d, FLOOR, CENTROIDS)
    assert attack["attack_type"] == "sql injection"
    assert attack["color"] == "#ef4444"
    assert attack["level"] == 12
