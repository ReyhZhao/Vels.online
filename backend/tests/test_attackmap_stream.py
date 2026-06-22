"""Attack Map SSE stream + config endpoint (PRD #594 #595/#600, ADR-0027).

The stream mirrors the Hunt stream: backfill the buffer on connect, then tail
seq > after. The infinite tail loop is bounded to one empty iteration in tests by
shrinking the idle limit so the generator drains and returns.
"""
import json
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from attackmap import views
from attackmap.buffer import AttackBuffer


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _bound_loop(monkeypatch):
    # Drain after the cold-join backfill + one empty tail loop, no real sleeping.
    monkeypatch.setattr(views, "_IDLE_LOOP_LIMIT", 0)
    monkeypatch.setattr(views, "_LOOP_SLEEP", 0)
    monkeypatch.setattr(views, "_STATS_EVERY", 1)


def _parse_sse(content):
    events, etype, data = [], None, []
    for line in content.splitlines():
        if line.startswith("event: "):
            etype = line[len("event: "):]
        elif line.startswith("data: "):
            data.append(line[len("data: "):])
        elif line == "" and etype is not None:
            events.append({"event": etype, "data": json.loads("".join(data)) if data else {}})
            etype, data = None, []
    return events


async def _collect(response):
    sc = response.streaming_content
    if hasattr(sc, "__aiter__"):
        return b"".join([chunk async for chunk in sc]).decode()
    return b"".join(sc).decode()


def _seed_buffer():
    buf = AttackBuffer()
    buf.append([
        {"level": 7, "color": "#f59e0b", "attack_type": "web", "src_country": "China",
         "src_lat": 1, "src_lng": 2, "dst_org_label": "Acme", "dst_lat": 3, "dst_lng": 4},
        {"level": 12, "color": "#ef4444", "attack_type": "sshd", "src_country": "Brazil",
         "src_lat": 5, "src_lng": 6, "dst_org_label": "Globex", "dst_lat": 7, "dst_lng": 8},
    ], now=1000)
    buf.set_stats({"top_countries": [["China", 5]], "per_minute": 3})


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="bob", password="p", is_staff=False)


@pytest.mark.django_db(transaction=True)
async def test_stream_backfills_buffer_then_emits_stats(async_client, staff):
    await async_client.aforce_login(staff)
    _seed_buffer()
    response = await async_client.get("/api/attack-map/stream/?after=-1")
    assert response.status_code == 200
    events = _parse_sse(await _collect(response))

    arcs = [e for e in events if e["event"] == "arc"]
    assert [a["data"]["srcCountry"] for a in arcs] == ["China", "Brazil"]
    assert arcs[0]["data"]["attackType"] == "web"          # camelCase wire shape
    assert any(e["event"] == "stats" for e in events)


@pytest.mark.django_db(transaction=True)
async def test_stream_resumes_from_after_seq(async_client, staff):
    await async_client.aforce_login(staff)
    _seed_buffer()
    response = await async_client.get("/api/attack-map/stream/?after=0")
    events = _parse_sse(await _collect(response))
    arcs = [e for e in events if e["event"] == "arc"]
    # Only seq 1 (Brazil) replayed; seq 0 already seen by the client.
    assert [a["data"]["seq"] for a in arcs] == [1]


@pytest.mark.django_db(transaction=True)
async def test_stream_is_staff_only(async_client, regular_user):
    await async_client.aforce_login(regular_user)
    response = await async_client.get("/api/attack-map/stream/?after=-1")
    assert response.status_code == 403


# ── config endpoint (slice #600) ───────────────────────────────────────────────
@pytest.mark.django_db
def test_config_get_returns_default_floor(staff):
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.get("/api/attack-map/config/")
    assert resp.status_code == 200
    assert resp.data["severity_floor"] == 3


@pytest.mark.django_db
def test_config_put_flips_floor_live(staff):
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.put("/api/attack-map/config/", {"severity_floor": 10}, format="json")
    assert resp.status_code == 200
    assert resp.data["severity_floor"] == 10
    assert client.get("/api/attack-map/config/").data["severity_floor"] == 10


@pytest.mark.django_db
def test_config_is_staff_only(regular_user):
    client = APIClient()
    client.force_authenticate(regular_user)
    assert client.get("/api/attack-map/config/").status_code == 403
