"""Redis attack buffer — count cap, age trim, seq monotonicity, stats (PRD #594 #595/#598)."""
import pytest
from django.core.cache import cache

from attackmap.buffer import AttackBuffer


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _attack(country="China"):
    return {"level": 7, "color": "#f59e0b", "src_country": country, "src_lat": 1, "src_lng": 2,
            "dst_org_label": "Acme", "dst_lat": 3, "dst_lng": 4, "attack_type": "web"}


def test_seq_is_monotonic_and_assigned():
    buf = AttackBuffer()
    seqs = buf.append([_attack(), _attack()], now=1000)
    assert seqs == [0, 1]
    more = buf.append([_attack()], now=1001)
    assert more == [2]


def test_count_cap_evicts_oldest():
    buf = AttackBuffer(maxlen=3, max_age_seconds=10_000)
    buf.append([_attack(str(i)) for i in range(5)], now=1000)
    remaining = buf.since(-1)
    assert len(remaining) == 3
    # The three newest (seqs 2,3,4) survive; oldest two evicted.
    assert [e["seq"] for e in remaining] == [2, 3, 4]


def test_since_returns_only_newer_in_order():
    buf = AttackBuffer()
    buf.append([_attack(), _attack(), _attack()], now=1000)
    after_first = buf.since(0)
    assert [e["seq"] for e in after_first] == [1, 2]


def test_age_trim_drops_old_entries_even_under_count_cap():
    buf = AttackBuffer(maxlen=500, max_age_seconds=900)
    buf.append([_attack()], now=1000)            # seq 0 at t=1000
    buf.append([_attack()], now=1000 + 950)      # seq 1 at t=1950 (>900s later)
    # Appending at 1950 trims entries older than 1950-900=1050 → seq 0 (t=1000) drops.
    remaining = buf.since(-1)
    assert [e["seq"] for e in remaining] == [1]


def test_trim_runs_without_append_during_quiet_periods():
    buf = AttackBuffer(maxlen=500, max_age_seconds=900)
    buf.append([_attack()], now=1000)
    buf.trim(now=1000 + 901)  # no new events, just age out
    assert buf.since(-1) == []


def test_stats_round_trip():
    buf = AttackBuffer()
    blob = {"top_countries": [["China", 5]], "per_minute": 12}
    buf.set_stats(blob)
    assert buf.get_stats() == blob
