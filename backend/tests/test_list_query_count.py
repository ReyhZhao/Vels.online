"""
Regression tests: N+1 queries are absent on high-traffic list endpoints.

Each test populates two batches of rows, captures the DB query count per
batch, and asserts the count stays constant as the row count grows.  A
growing count is a sign that the list view is issuing per-row queries instead
of bulk prefetches / annotations.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from incidents.models import Asset, Incident, IncidentAsset, IncidentDelegation, IOC
from security.models import Organization, OrganizationMembership


_seq = [0]


def _next_id():
    _seq[0] += 1
    return _seq[0]


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme QC", slug="acme-qc", wazuh_group="acme-qc")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff-qc", password="p", is_staff=True)


def _make_incident(org):
    n = _next_id()
    return Incident.objects.create(
        organization=org,
        display_id=f"INC-QC-{n:06d}",
        title="Query count test",
        severity="medium",
        tlp="amber",
        state="new",
    )


def _make_asset(org):
    n = _next_id()
    return Asset.objects.create(
        organization=org,
        kind=Asset.KIND_HOST,
        name=f"host-{n}",
        agent_name=f"host-{n}",
        ip_address="10.0.0.1",
    )


# ── incident list ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_incident_list_query_count_constant(client, staff, org):
    """List view prefetches/annotates all relations; query count must not scale with row count."""
    client.force_login(staff)

    def _populate(n):
        for _ in range(n):
            inc = _make_incident(org)
            asset = _make_asset(org)
            IncidentAsset.objects.create(incident=inc, asset=asset)
            IOC.objects.create(incident=inc, kind="ip", value="1.1.1.1")
            IncidentDelegation.objects.create(incident=inc, user=staff)

    _populate(3)
    with CaptureQueriesContext(connection) as ctx_a:
        r = client.get("/api/incidents/")
    assert r.status_code == 200
    q_a = len(ctx_a)

    _populate(3)
    with CaptureQueriesContext(connection) as ctx_b:
        r = client.get("/api/incidents/")
    assert r.status_code == 200
    q_b = len(ctx_b)

    assert q_b <= q_a + 2, (
        f"Incident list query count grew from {q_a} (3 rows) to {q_b} (6 rows) — "
        "N+1 regression."
    )


# ── asset list ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_asset_list_query_count_constant(client, staff, org):
    """List view prefetches nat_exposures / route_exposures; query count must not scale with row count."""
    client.force_login(staff)

    def _populate(n):
        for _ in range(n):
            _make_asset(org)

    _populate(3)
    with CaptureQueriesContext(connection) as ctx_a:
        r = client.get("/api/assets/")
    assert r.status_code == 200
    q_a = len(ctx_a)

    _populate(3)
    with CaptureQueriesContext(connection) as ctx_b:
        r = client.get("/api/assets/")
    assert r.status_code == 200
    q_b = len(ctx_b)

    assert q_b <= q_a + 2, (
        f"Asset list query count grew from {q_a} (3 rows) to {q_b} (6 rows) — "
        "N+1 regression."
    )
