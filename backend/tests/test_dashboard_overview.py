import datetime
import itertools

import pytest
from django.utils import timezone

from alerts.models import Alert
from incidents.models import Incident
from ingress.models import Route
from security.models import Organization, OrganizationMembership


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name="Other", slug="other", wazuh_group="other")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="alice", password="pass", is_staff=False)
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


_seq = itertools.count(1)


def _incident(org, **kwargs):
    defaults = {"title": "Test incident", "severity": "medium", "state": "new",
                "display_id": f"INC-TEST-{next(_seq):04d}"}
    defaults.update(kwargs)
    return Incident.objects.create(organization=org, **defaults)


def _alert(org, **kwargs):
    defaults = {"title": "Test alert", "state": "new", "severity": "low",
                "display_id": f"AL-TEST-{next(_seq):04d}"}
    defaults.update(kwargs)
    return Alert.objects.create(organization=org, **defaults)


# ── auth & scoping ───────────────────────────────────────────────────────────


def test_unauthenticated_returns_401(client, acme):
    resp = client.get("/api/dashboard/overview/?org=acme")
    assert resp.status_code == 401


def test_org_required(client, member):
    client.force_login(member)
    resp = client.get("/api/dashboard/overview/")
    assert resp.status_code == 400


def test_non_member_org_returns_403(client, member, other_org):
    client.force_login(member)
    resp = client.get("/api/dashboard/overview/?org=other")
    assert resp.status_code == 403


def test_unknown_org_returns_404(client, staff_user):
    client.force_login(staff_user)
    resp = client.get("/api/dashboard/overview/?org=nope")
    assert resp.status_code == 404


def test_counts_are_scoped_to_org(client, staff_user, acme, other_org):
    _incident(acme, state="new")
    _incident(other_org, state="new")
    _alert(other_org)
    client.force_login(staff_user)
    resp = client.get("/api/dashboard/overview/?org=acme")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incidents"]["open_total"] == 1
    assert data["alerts"]["new_total"] == 0


# ── incidents block ──────────────────────────────────────────────────────────


def test_incident_breakdowns(client, member, acme):
    _incident(acme, state="new", severity="critical")
    _incident(acme, state="in_progress", severity="high")
    _incident(acme, state="in_progress", severity="medium")
    _incident(acme, state="closed", severity="low", closure_reason="resolved")

    client.force_login(member)
    resp = client.get("/api/dashboard/overview/?org=acme")
    assert resp.status_code == 200
    inc = resp.json()["incidents"]
    assert inc["open_total"] == 3
    assert inc["by_state"]["new"] == 1
    assert inc["by_state"]["in_progress"] == 2
    assert inc["by_severity"]["critical"] == 1
    assert inc["by_severity"]["high"] == 1
    # closed incident excluded from open breakdowns
    assert inc["by_severity"]["low"] == 0
    assert inc["created_7d"] == 4
    assert inc["closed_7d"] == 1


def test_recent_lists_latest_open_incidents(client, member, acme):
    for n in range(7):
        _incident(acme, title=f"Incident {n}")
    _incident(acme, title="Closed one", state="closed", closure_reason="resolved")

    client.force_login(member)
    data = client.get("/api/dashboard/overview/?org=acme").json()
    recent = data["incidents"]["recent"]
    assert len(recent) == 5
    assert recent[0]["title"] == "Incident 6"
    assert all(r["state"] != "closed" for r in recent)
    assert {"display_id", "title", "severity", "state", "created_at", "assignee"} <= set(recent[0])


# ── alerts block ─────────────────────────────────────────────────────────────


def test_alert_stats(client, member, acme):
    _alert(acme, severity="critical")
    _alert(acme, severity="critical")
    _alert(acme, severity=None)
    _alert(acme, state="ignored", severity="low")

    client.force_login(member)
    data = client.get("/api/dashboard/overview/?org=acme").json()
    al = data["alerts"]
    assert al["new_total"] == 3
    assert al["last_24h"] == 4
    assert al["by_severity"]["critical"] == 2
    assert al["unrated"] == 1
    assert len(al["daily_7d"]) == 7
    assert al["daily_7d"][-1]["count"] == 4


def test_alert_daily_buckets_old_alerts_excluded(client, member, acme):
    a = _alert(acme)
    Alert.objects.filter(pk=a.pk).update(created_at=timezone.now() - datetime.timedelta(days=10))

    client.force_login(member)
    data = client.get("/api/dashboard/overview/?org=acme").json()
    assert data["alerts"]["last_24h"] == 0
    assert sum(b["count"] for b in data["alerts"]["daily_7d"]) == 0


# ── routes block ─────────────────────────────────────────────────────────────


def test_route_stats(client, member, acme):
    Route.objects.create(fqdn="a.acme.io", backend_host="10.0.0.1", backend_port=80,
                         organization=acme, status="active")
    Route.objects.create(fqdn="b.acme.io", backend_host="10.0.0.2", backend_port=80,
                         organization=acme, status="error")

    client.force_login(member)
    data = client.get("/api/dashboard/overview/?org=acme").json()
    assert data["routes"]["total"] == 2
    assert data["routes"]["by_status"]["active"] == 1
    assert data["routes"]["by_status"]["error"] == 1
    assert data["routes"]["by_status"]["pending"] == 0


# ── staff block ──────────────────────────────────────────────────────────────


def test_staff_block_present_for_staff_only(client, staff_user, member, acme):
    _incident(acme, state="new")
    _incident(acme, state="pending_closure")
    _incident(acme, state="in_progress", assignee=staff_user)

    client.force_login(member)
    assert "staff" not in client.get("/api/dashboard/overview/?org=acme").json()

    client.force_login(staff_user)
    staff = client.get("/api/dashboard/overview/?org=acme").json()["staff"]
    assert staff["needs_triage"] == 1
    assert staff["pending_closure"] == 1
    assert staff["unassigned_open"] == 2
