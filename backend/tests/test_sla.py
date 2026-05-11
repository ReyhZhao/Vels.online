"""
Tests for per-severity SLA computation on the incident serializer (issue #111).
"""
import pytest
from datetime import timedelta
from django.utils import timezone

from security.models import Organization
from incidents.models import Incident


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


_ctr = [0]


def make_incident(org, **kwargs):
    _ctr[0] += 1
    defaults = dict(title="T", display_id=f"INC-SLA-{_ctr[0]:04d}", severity="high", state="new", tlp="amber")
    defaults.update(kwargs)
    return Incident.objects.create(organization=org, **defaults)


def sla(client, inc, field):
    r = client.get(f"/api/incidents/{inc.display_id}/")
    assert r.status_code == 200
    return r.json()[field]


# ── serializer shape ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_serializer_returns_sla_shape(client, staff, acme):
    inc = make_incident(acme)
    client.force_login(staff)
    r = client.get(f"/api/incidents/{inc.display_id}/")
    data = r.json()
    for field in ("response_sla", "resolve_sla"):
        s = data[field]
        assert s is not None
        for key in ("target_seconds", "elapsed_seconds", "remaining_seconds", "breached", "applies"):
            assert key in s, f"{field} missing key {key!r}"


# ── target lookup ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize("severity,response_s,resolve_s", [
    ("critical", 15 * 60,      4 * 3600),
    ("high",     1 * 3600,    24 * 3600),
    ("medium",   4 * 3600, 3 * 24 * 3600),
    ("low",     24 * 3600, 7 * 24 * 3600),
])
def test_target_lookup_per_severity(client, staff, acme, severity, response_s, resolve_s):
    inc = make_incident(acme, severity=severity, state="new")
    client.force_login(staff)
    assert sla(client, inc, "response_sla")["target_seconds"] == response_s
    assert sla(client, inc, "resolve_sla")["target_seconds"] == resolve_s


@pytest.mark.django_db
def test_sla_none_for_info_severity(client, staff, acme):
    inc = make_incident(acme, severity="info", state="new")
    client.force_login(staff)
    r = client.get(f"/api/incidents/{inc.display_id}/")
    assert r.json()["response_sla"] is None
    assert r.json()["resolve_sla"] is None


# ── applies flag ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_response_sla_applies_only_when_new(client, staff, acme):
    inc_new = make_incident(acme, severity="high", state="new")
    inc_ip  = make_incident(acme, severity="high", state="in_progress")
    client.force_login(staff)
    assert sla(client, inc_new, "response_sla")["applies"] is True
    assert sla(client, inc_ip,  "response_sla")["applies"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["triaged", "in_progress", "on_hold"])
def test_response_sla_applies_false_for_non_new_states(client, staff, acme, state):
    inc = make_incident(acme, severity="high", state=state)
    client.force_login(staff)
    assert sla(client, inc, "response_sla")["applies"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["new", "triaged", "in_progress", "on_hold"])
def test_resolve_sla_applies_for_active_states(client, staff, acme, state):
    inc = make_incident(acme, severity="high", state=state)
    client.force_login(staff)
    assert sla(client, inc, "resolve_sla")["applies"] is True


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["resolved", "closed"])
def test_resolve_sla_applies_false_when_terminal(client, staff, acme, state):
    inc = make_incident(acme, severity="high", state=state)
    client.force_login(staff)
    assert sla(client, inc, "resolve_sla")["applies"] is False


# ── breached / remaining ──────────────────────────────────────────────────────

@pytest.mark.django_db
def test_not_breached_when_within_target(client, staff, acme):
    inc = make_incident(acme, severity="critical", state="new")
    client.force_login(staff)
    s = sla(client, inc, "response_sla")
    assert s["breached"] is False
    assert s["remaining_seconds"] > 0


@pytest.mark.django_db
def test_breached_when_elapsed_exceeds_target(client, staff, acme):
    inc = make_incident(acme, severity="critical", state="new")
    Incident.objects.filter(pk=inc.pk).update(created_at=timezone.now() - timedelta(minutes=20))
    client.force_login(staff)
    s = sla(client, inc, "response_sla")
    assert s["breached"] is True
    assert s["remaining_seconds"] < 0


@pytest.mark.django_db
def test_elapsed_seconds_is_approximate(client, staff, acme):
    inc = make_incident(acme, severity="high", state="new")
    Incident.objects.filter(pk=inc.pk).update(created_at=timezone.now() - timedelta(hours=2))
    client.force_login(staff)
    s = sla(client, inc, "resolve_sla")
    assert 7100 < s["elapsed_seconds"] < 7300


# ── list endpoint also returns sla fields ─────────────────────────────────────

@pytest.mark.django_db
def test_list_endpoint_includes_sla_fields(client, staff, acme):
    make_incident(acme, severity="high", state="new")
    client.force_login(staff)
    r = client.get("/api/incidents/")
    first = r.json()["results"][0]
    assert "response_sla" in first
    assert "resolve_sla" in first
