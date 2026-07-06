"""Precedent retrieval for the Triage Classify phase (ADR-0030/0031, slice #660).

Isolation-critical: a precedent is only ever drawn from the incident's OWN organisation.
"""
import pytest

from incidents.memory.precedents import build_precedents, build_precedent_context
from incidents.models import Asset, Comment, IncidentAsset, IOC, Incident, Subject
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def globex(db):
    return Organization.objects.create(name="Globex", slug="globex", wazuh_group="globex")


def make_incident(org, *, state="new", severity="medium", subject=None, closure_reason=None):
    n = Incident.objects.count()
    return Incident.objects.create(
        organization=org, title="Suspicious login from 10.0.0.9", description="failed SSH",
        display_id=f"INC-2026-{n + 1:04d}", state=state, severity=severity,
        subject=subject, closure_reason=closure_reason,
    )


def add_ioc(incident, value, kind="ip"):
    return IOC.objects.create(incident=incident, kind=kind, value=value)


def link_asset(incident, asset):
    IncidentAsset.objects.create(incident=incident, asset=asset)


def make_asset(org, agent_name="web-01", ip="10.0.0.9"):
    return Asset.objects.create(organization=org, kind="host", name=agent_name,
                                agent_name=agent_name, ip_address=ip)


# ── matching ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_matches_resolved_incident_sharing_an_ioc(acme):
    past = make_incident(acme, state="closed", closure_reason="false_positive")
    add_ioc(past, "1.2.3.4")
    Comment.objects.create(incident=past, body="Benign — this is our VPN egress IP.", kind="user")

    current = make_incident(acme)
    add_ioc(current, "1.2.3.4")

    precedents = build_precedents(current)
    assert [p["display_id"] for p in precedents] == [past.display_id]
    assert precedents[0]["closure_reason"] == "false_positive"
    assert "VPN egress" in precedents[0]["resolution_comments"][0]


@pytest.mark.django_db
def test_matches_resolved_incident_sharing_an_asset(acme):
    asset = make_asset(acme, agent_name="db-01", ip="10.0.0.50")
    past = make_incident(acme, state="closed", closure_reason="resolved", severity="high")
    link_asset(past, asset)
    current = make_incident(acme)
    link_asset(current, asset)

    precedents = build_precedents(current)
    assert [p["display_id"] for p in precedents] == [past.display_id]
    assert precedents[0]["final_severity"] == "high"


@pytest.mark.django_db
def test_enrichment_carries_final_subject(acme):
    subj = Subject.objects.create(name="Brute Force", slug="brute-force")
    past = make_incident(acme, state="closed", closure_reason="resolved", subject=subj)
    add_ioc(past, "9.9.9.9")
    current = make_incident(acme)
    add_ioc(current, "9.9.9.9")

    precedents = build_precedents(current)
    assert precedents[0]["final_subject"] == "Brute Force"
    assert precedents[0]["corrected_from_agent"] is False


# ── the isolation invariant (ADR-0031) ─────────────────────────────────────────


@pytest.mark.django_db
def test_never_returns_another_orgs_incident(acme, globex):
    foreign = make_incident(globex, state="closed", closure_reason="false_positive")
    add_ioc(foreign, "1.2.3.4")
    current = make_incident(acme)
    add_ioc(current, "1.2.3.4")

    assert build_precedents(current) == []


# ── only concluded cases ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ignores_open_incident_sharing_an_ioc(acme):
    open_inc = make_incident(acme, state="in_progress")
    add_ioc(open_inc, "1.2.3.4")
    current = make_incident(acme)
    add_ioc(current, "1.2.3.4")

    assert build_precedents(current) == []


@pytest.mark.django_db
def test_returns_empty_without_matchable_keys(acme):
    make_incident(acme, state="closed", closure_reason="resolved")
    current = make_incident(acme)  # no IOCs, no assets
    assert build_precedents(current) == []


@pytest.mark.django_db
def test_context_block_renders_precedents(acme):
    past = make_incident(acme, state="closed", closure_reason="false_positive")
    add_ioc(past, "1.2.3.4")
    current = make_incident(acme)
    add_ioc(current, "1.2.3.4")

    block = build_precedent_context(build_precedents(current))
    assert past.display_id in block
    assert "false_positive" in block
    assert build_precedent_context([]) == ""
