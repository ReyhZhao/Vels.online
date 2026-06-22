"""Presence registry + snapshot producer (PRD #594 #595/#598, ADR-0027).

Asserts: any_present() true after a heartbeat / false after TTL; the producer
short-circuits (no OpenSearch call) when nobody is present; and a present-and-running
tick projects hits → arcs, resolves destinations, and writes the stats blob.
"""
import pytest
from unittest.mock import MagicMock
from django.core.cache import cache

from attackmap import presence
from attackmap.buffer import AttackBuffer
from attackmap.producer import run_snapshot_tick
from security.models import Organization


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── presence registry ────────────────────────────────────────────────────────
def test_any_present_true_after_heartbeat_false_after_ttl():
    assert presence.any_present(now=1000) is False
    presence.heartbeat("conn-a", now=1000)
    assert presence.any_present(now=1001) is True
    # Past the TTL window the heartbeat lapses → no presence (self-heals).
    assert presence.any_present(now=1000 + presence.TTL_SECONDS + 1) is False


def test_drop_removes_a_connection():
    presence.heartbeat("conn-a", now=1000)
    presence.drop("conn-a")
    assert presence.any_present(now=1000) is False


# ── producer ──────────────────────────────────────────────────────────────────
def _snapshot():
    return {
        "hits": [
            {"_id": "h1", "_source": {
                "rule": {"level": 10, "groups": ["sshd", "attack"]},
                "agent": {"id": "001"},
                "@timestamp": "2026-06-22T10:00:00Z",
                "GeoLocation": {"country_name": "China", "location": {"lat": 39.9, "lon": 116.4}},
            }},
        ],
        "total": 30,
        "aggregations": {
            "by_geo_country": {"buckets": [{"key": "China", "doc_count": 20}]},
            "by_src_country": {"buckets": [{"key": "Reserved", "doc_count": 99}, {"key": "Brazil", "doc_count": 5}]},
            "by_attack_type": {"buckets": [{"key": "sshd", "doc_count": 18}, {"key": "attack", "doc_count": 30}]},
        },
        "window_minutes": 15,
    }


def _clients():
    os_client = MagicMock()
    os_client.get_attack_snapshot.return_value = _snapshot()
    wazuh = MagicMock()
    wazuh.get_agents.return_value = [{"id": "001"}]
    return os_client, wazuh


def test_producer_short_circuits_when_no_presence():
    os_client, wazuh = _clients()
    result = run_snapshot_tick(os_client, wazuh, now=1000)
    assert result["skipped"] is True
    os_client.get_attack_snapshot.assert_not_called()


@pytest.mark.django_db
def test_producer_projects_hits_and_writes_stats_when_present():
    Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme", latitude=51.5, longitude=-0.12)
    presence.heartbeat("conn-a", now=1000)
    os_client, wazuh = _clients()

    result = run_snapshot_tick(os_client, wazuh, floor=3, now=1000)

    assert result["skipped"] is False
    assert result["appended"] == 1
    arcs = AttackBuffer().since(-1)
    assert len(arcs) == 1
    arc = arcs[0]
    assert arc["src_country"] == "China"
    assert arc["dst_org_label"] == "Acme"          # agent 001 → Acme
    assert (arc["dst_lat"], arc["dst_lng"]) == (51.5, -0.12)
    assert "agent_id" not in arc                    # stripped before buffering

    stats = AttackBuffer().get_stats()
    assert ["China", 20] in stats["top_countries"]
    assert all(c[0] != "Reserved" for c in stats["top_countries"])  # sentinel excluded
    assert stats["per_minute"] == 2                 # round(30/15)


@pytest.mark.django_db
def test_producer_dedupes_repeated_hits_across_ticks():
    Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme", latitude=51.5, longitude=-0.12)
    presence.heartbeat("conn-a", now=1000)
    os_client, wazuh = _clients()

    run_snapshot_tick(os_client, wazuh, floor=3, now=1000)
    presence.heartbeat("conn-a", now=1010)
    second = run_snapshot_tick(os_client, wazuh, floor=3, now=1010)

    # Same hit id "h1" returned again → not re-appended as a duplicate arc.
    assert second["appended"] == 0
    assert len(AttackBuffer().since(-1)) == 1
