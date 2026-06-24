"""Tests for Incident Presence (PRD #605, ADR-0028) — registry, SSE view, POST, AI bridge."""
import json
from unittest.mock import patch

import pytest

from incidents import presence, views as incident_views
from incidents.models import Incident
from security.models import Organization


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def _bound_presence_loop(monkeypatch):
    """Bound the SSE presence loop so it drains after one idle iteration in tests."""
    monkeypatch.setattr(incident_views, "_PRESENCE_IDLE_LOOP_LIMIT", 0)
    monkeypatch.setattr(incident_views, "_PRESENCE_LOOP_SLEEP", 0)


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(
        organization=acme, title="Test", display_id="INC-PRES-1", state="new"
    )


# ── registry: viewing roster + TTL ────────────────────────────────────────────


@pytest.mark.django_db
def test_heartbeat_registers_viewing(incident):
    presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1, now=1000)
    r = presence.roster(incident.id, now=1001)
    assert len(r) == 1
    assert r[0]["display_name"] == "dana"
    assert r[0]["activity"] == "viewing"
    assert r[0]["actor_kind"] == "human"


@pytest.mark.django_db
def test_ttl_expiry_drops_actor(incident):
    presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1, now=1000)
    # Past the 15s TTL with no further heartbeat.
    assert presence.roster(incident.id, now=1000 + presence.TTL_SECONDS + 1) == []


@pytest.mark.django_db
def test_clean_drop_removes_immediately(incident):
    presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1, now=1000)
    presence.drop(incident.id, "user:1")
    assert presence.roster(incident.id, now=1001) == []


@pytest.mark.django_db
def test_heartbeat_preserves_declared_activity(incident):
    presence.set_activity(incident.id, "user:1", "working", target=42,
                          display_name="dana", actor_id=1, now=1000)
    # A later passive viewing beat must not clobber the declared working activity.
    presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1, now=1005)
    r = presence.roster(incident.id, now=1006)
    assert r[0]["activity"] == "working"
    assert r[0]["target"] == 42


@pytest.mark.django_db
def test_set_activity_reverts_to_viewing(incident):
    presence.set_activity(incident.id, "user:1", "working", target=42,
                          display_name="dana", actor_id=1, now=1000)
    presence.set_activity(incident.id, "user:1", "viewing", target=None,
                          display_name="dana", actor_id=1, now=1001)
    r = presence.roster(incident.id, now=1002)
    assert r[0]["activity"] == "viewing"
    assert r[0]["target"] is None


# ── comment-edit soft lock ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_acquire_lock_grants_first_denies_second(incident):
    granted, holder = presence.acquire_comment_lock(
        incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1000)
    assert granted is True and holder is None

    granted2, holder2 = presence.acquire_comment_lock(
        incident.id, "user:2", 7, display_name="eve", actor_id=2, now=1001)
    assert granted2 is False
    assert holder2["display_name"] == "dana"


@pytest.mark.django_db
def test_lock_idle_auto_release(incident):
    presence.acquire_comment_lock(incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1000)
    # Keep the actor present (heartbeat) but past the idle window with no keystroke.
    t = 1000 + presence.LOCK_IDLE_SECONDS + 1
    presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1, now=t)
    # Lock is no longer held; a second actor can now acquire.
    granted, _ = presence.acquire_comment_lock(incident.id, "user:2", 7, display_name="eve", actor_id=2, now=t + 1)
    assert granted is True
    # And the first actor has reverted to viewing in the roster.
    holder = presence.comment_lock_holder(incident.id, 7, exclude_actor="user:2", now=t + 1)
    assert holder is None


@pytest.mark.django_db
def test_refresh_lock_holds(incident):
    presence.acquire_comment_lock(incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1000)
    # Continuous typing: keystrokes every 10s (within the 15s TTL) keep both the
    # presence record alive and the idle window pushed forward, past the original
    # ~5-min idle deadline.
    t = 1000
    for step in range(1, 33):
        t = 1000 + step * 10
        presence.refresh_comment_lock(incident.id, "user:1", 7, now=t)
    assert t > 1000 + presence.LOCK_IDLE_SECONDS  # we are past the original deadline
    granted, holder = presence.acquire_comment_lock(incident.id, "user:2", 7, display_name="eve", actor_id=2, now=t + 1)
    assert granted is False
    assert holder["display_name"] == "dana"


@pytest.mark.django_db
def test_lock_released_on_drop(incident):
    presence.acquire_comment_lock(incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1000)
    presence.drop(incident.id, "user:1")
    granted, _ = presence.acquire_comment_lock(incident.id, "user:2", 7, display_name="eve", actor_id=2, now=1001)
    assert granted is True


@pytest.mark.django_db
def test_reacquire_own_lock_refreshes(incident):
    presence.acquire_comment_lock(incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1000)
    granted, holder = presence.acquire_comment_lock(incident.id, "user:1", 7, display_name="dana", actor_id=1, now=1002)
    assert granted is True and holder is None


# ── fail-open / degrade-invisible ─────────────────────────────────────────────


@pytest.mark.django_db
def test_roster_fails_open_to_empty(incident):
    with patch("incidents.presence.cache.get", side_effect=RuntimeError("redis down")):
        assert presence.roster(incident.id) == []


@pytest.mark.django_db
def test_acquire_lock_fails_open_to_granted(incident):
    with patch("incidents.presence.cache.get", side_effect=RuntimeError("redis down")):
        granted, holder = presence.acquire_comment_lock(incident.id, "user:1", 7)
    assert granted is True and holder is None


@pytest.mark.django_db
def test_heartbeat_fails_open_silently(incident):
    with patch("incidents.presence.cache.get", side_effect=RuntimeError("redis down")):
        presence.heartbeat(incident.id, "user:1", display_name="dana", actor_id=1)  # no raise


# ── SSE view + POST endpoint ──────────────────────────────────────────────────


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="soc", password="p", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="p", is_staff=False)


@pytest.mark.django_db(transaction=True)
async def test_presence_stream_staff_gate(async_client, regular_user, incident):
    await async_client.aforce_login(regular_user)
    response = await async_client.get(f"/api/incidents/{incident.display_id}/presence/")
    assert response.status_code == 403
    assert not response.streaming


@pytest.mark.django_db(transaction=True)
async def test_presence_stream_emits_roster_snapshot(async_client, staff, incident):
    await async_client.aforce_login(staff)
    response = await async_client.get(f"/api/incidents/{incident.display_id}/presence/")
    assert response.status_code == 200
    # Read only the first chunk of the infinite stream.
    first = None
    async for chunk in response.streaming_content:
        first = chunk.decode()
        break
    assert first is not None
    assert "event: roster" in first
    data = json.loads(first.split("data: ", 1)[1].split("\n\n")[0])
    assert any(r["display_name"] == "soc" and r["activity"] == "viewing" for r in data)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("_bound_presence_loop")
async def test_presence_stream_drop_actor_on_disconnect(async_client, staff, incident):
    """The viewer is removed from the registry when the stream drains (clean disconnect)."""
    await async_client.aforce_login(staff)
    response = await async_client.get(f"/api/incidents/{incident.display_id}/presence/")
    assert response.status_code == 200
    # Drain the stream — the bounded loop runs once (emit) then terminates on idle,
    # triggering the finally block which calls drop().
    content = b""
    async for chunk in response.streaming_content:
        content += chunk
    # At least one roster snapshot was emitted.
    assert b"event: roster" in content
    # The actor is no longer in the registry after the generator's finally ran.
    assert presence.roster(incident.id) == []


@pytest.mark.django_db
def test_presence_post_working(client, staff, incident):
    client.force_login(staff)
    resp = client.post(
        f"/api/incidents/{incident.display_id}/presence/",
        {"activity": "working", "target": 42},
        content_type="application/json",
    )
    assert resp.status_code == 200
    r = presence.roster(incident.id)
    assert r[0]["activity"] == "working"
    assert r[0]["target"] == 42


@pytest.mark.django_db
def test_presence_post_staff_gate(client, regular_user, incident):
    client.force_login(regular_user)
    resp = client.post(
        f"/api/incidents/{incident.display_id}/presence/",
        {"activity": "working", "target": 42},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_presence_post_comment_lock_conflict(client, staff, incident, django_user_model):
    other = django_user_model.objects.create_user(username="eve", password="p", is_staff=True)
    # eve already holds the lock on comment 9.
    presence.acquire_comment_lock(incident.id, presence.human_actor_key(other.id), 9,
                                  display_name="eve", actor_id=other.id)
    client.force_login(staff)
    resp = client.post(
        f"/api/incidents/{incident.display_id}/presence/",
        {"activity": "editing", "target": 9},
        content_type="application/json",
    )
    assert resp.status_code == 409
    assert resp.json()["holder"] == "eve"


@pytest.mark.django_db
def test_presence_post_editing_compose_unlocked(client, staff, incident):
    """Composing a new comment (editing, no target) is advisory, never 409."""
    client.force_login(staff)
    resp = client.post(
        f"/api/incidents/{incident.display_id}/presence/",
        {"activity": "editing", "target": None},
        content_type="application/json",
    )
    assert resp.status_code == 200


# ── AI presence bridge (slice #610) ───────────────────────────────────────────


@pytest.mark.django_db
def test_ai_presence_context_registers_and_drops(incident):
    from incidents.presence_bridge import ai_presence

    with ai_presence(incident.id, "Triage Agent") as ai:
        ai.on_event({"type": "tool", "tool": "search"})
        r = presence.roster(incident.id)
        assert len(r) == 1
        assert r[0]["actor_kind"] == "ai"
        assert r[0]["display_name"] == "Triage Agent"
        assert r[0]["activity"] == "working"
    # Dropped in finally.
    assert presence.roster(incident.id) == []


@pytest.mark.django_db
def test_ai_presence_drops_on_error(incident):
    from incidents.presence_bridge import ai_presence

    with pytest.raises(ValueError):
        with ai_presence(incident.id, "Triage Agent"):
            raise ValueError("boom")
    assert presence.roster(incident.id) == []


@pytest.mark.django_db
def test_ai_presence_attributed_to_invoker(incident):
    from incidents.presence_bridge import AIPresence

    ai = AIPresence(incident.id, "Incident Assistant", run_by="dana")
    ai.start()
    r = presence.roster(incident.id)
    assert r[0]["run_by"] == "dana"
    assert r[0]["display_name"] == "Incident Assistant"
    ai.drop()
