"""
Backend tests for the Incident Trend feature (PRD #614, slice #615).

Two layers:
  * the aggregation module (`compute_incident_trend`) — the deep module, given
    the most coverage: bucketing incl. empty days, top-N selection, Other
    collapse, Unclassified/null, tie-breaking, empty population, window
    boundaries;
  * the `/api/incidents/trend/` endpoint — tenant scope, tab, filter honouring,
    ignoring its own `subject`/`created_within`, `days` validation, shape.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from incidents.models import Incident, Subject
from incidents.services.incident_queryset import build_incident_queryset
from incidents.services.incident_trend import compute_incident_trend
from security.models import Organization, OrganizationMembership


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def infra(db):
    # Seeded idempotently by a data migration (ADR-0017); fetch, don't recreate.
    return Organization.get_infrastructure()


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="p")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


_counter = [0]


def make_incident(org, created_at=None, subject=None, **kwargs):
    _counter[0] += 1
    defaults = dict(
        title="Test",
        display_id=f"TR-{_counter[0]:05d}",
        severity="medium",
        tlp="amber",
        state="new",
    )
    defaults.update(kwargs)
    inc = Incident.objects.create(organization=org, subject=subject, **defaults)
    if created_at is not None:
        Incident.objects.filter(pk=inc.pk).update(created_at=created_at)
    return inc


def subject(name):
    # Migration 0004 seeds some real Subjects (Phishing, Malware, …); give every
    # test Subject a unique slug so we never collide with a seeded one.
    _counter[0] += 1
    return Subject.objects.create(name=name, slug=f"trend-{_counter[0]}")


# ── aggregation: bucketing ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_one_bucket_per_day_including_empty_days(acme):
    now = timezone.now()
    make_incident(acme, created_at=now)
    make_incident(acme, created_at=now - timedelta(days=3))

    result = compute_incident_trend(Incident.objects.all(), days=7, now=now)

    # Exactly 7 daily buckets, contiguous, oldest first.
    assert len(result["buckets"]) == 7
    dates = [b["date"] for b in result["buckets"]]
    assert dates == sorted(dates)
    today = timezone.localdate(now)
    assert result["buckets"][-1]["date"] == today.isoformat()
    assert result["buckets"][0]["date"] == (today - timedelta(days=6)).isoformat()
    # Empty days carry an empty counts map (not absent).
    assert any(b["counts"] == {} for b in result["buckets"])


@pytest.mark.django_db
def test_unclassified_bucket_for_null_subject(acme):
    now = timezone.now()
    make_incident(acme, created_at=now, subject=None)
    make_incident(acme, created_at=now, subject=None)

    result = compute_incident_trend(Incident.objects.all(), days=7, now=now)

    keys = {s["key"] for s in result["subjects"]}
    assert "unclassified" in keys
    unclassified = next(s for s in result["subjects"] if s["key"] == "unclassified")
    assert unclassified["subject_id"] is None
    assert unclassified["kind"] == "unclassified"
    last = result["buckets"][-1]["counts"]
    assert last["unclassified"] == 2


@pytest.mark.django_db
def test_real_subject_series_and_counts(acme):
    now = timezone.now()
    bf = subject("Brute Force")
    make_incident(acme, created_at=now, subject=bf)
    make_incident(acme, created_at=now - timedelta(days=1), subject=bf)

    result = compute_incident_trend(Incident.objects.all(), days=7, now=now)

    real = [s for s in result["subjects"] if s["kind"] == "real"]
    assert len(real) == 1
    assert real[0]["subject_id"] == bf.id
    assert real[0]["name"] == "Brute Force"
    assert real[0]["key"] == str(bf.id)
    assert result["buckets"][-1]["counts"][str(bf.id)] == 1
    assert result["buckets"][-2]["counts"][str(bf.id)] == 1


# ── aggregation: top-N + Other collapse ──────────────────────────────────────

@pytest.mark.django_db
def test_top_n_selection_and_other_collapse(acme):
    now = timezone.now()
    # 9 distinct subjects with decreasing volume; top_n=7 → 2 fold into Other.
    subjects = []
    for i in range(9):
        s = subject(f"S{i:02d}")
        subjects.append(s)
        for _ in range(10 - i):  # S00 has 10, S08 has 2
            make_incident(acme, created_at=now, subject=s)

    result = compute_incident_trend(Incident.objects.all(), days=7, top_n=7, now=now)

    real = [s for s in result["subjects"] if s["kind"] == "real"]
    assert len(real) == 7
    # The 7 highest-volume subjects are the distinct ones.
    assert {s["subject_id"] for s in real} == {s.id for s in subjects[:7]}
    other = next(s for s in result["subjects"] if s["key"] == "other")
    assert other["subject_id"] is None
    assert other["kind"] == "other"
    # Other holds the two long-tail subjects' incidents: S07 (3) + S08 (2) = 5.
    assert result["buckets"][-1]["counts"]["other"] == 5


@pytest.mark.django_db
def test_no_other_series_when_within_top_n(acme):
    now = timezone.now()
    for i in range(3):
        make_incident(acme, created_at=now, subject=subject(f"S{i}"))
    result = compute_incident_trend(Incident.objects.all(), days=7, top_n=7, now=now)
    keys = {s["key"] for s in result["subjects"]}
    assert "other" not in keys


@pytest.mark.django_db
def test_tie_breaking_is_deterministic_by_name(acme):
    now = timezone.now()
    # Three subjects tied at exactly one incident each; top_n=2 keeps two and
    # folds the third. Tie-break is by name asc, so "Charlie" is folded.
    a = subject("Alpha")
    b = subject("Bravo")
    c = subject("Charlie")
    make_incident(acme, created_at=now, subject=a)
    make_incident(acme, created_at=now, subject=b)
    make_incident(acme, created_at=now, subject=c)

    result = compute_incident_trend(Incident.objects.all(), days=7, top_n=2, now=now)

    real_ids = [s["subject_id"] for s in result["subjects"] if s["kind"] == "real"]
    assert real_ids == [a.id, b.id]
    assert any(s["key"] == "other" for s in result["subjects"])


# ── aggregation: empty + boundaries ──────────────────────────────────────────

@pytest.mark.django_db
def test_empty_population_returns_well_formed_result(acme):
    now = timezone.now()
    result = compute_incident_trend(Incident.objects.none(), days=30, now=now)
    assert result["subjects"] == []
    assert len(result["buckets"]) == 30
    assert all(b["counts"] == {} for b in result["buckets"])


@pytest.mark.django_db
def test_window_boundary_just_inside_and_outside(acme):
    now = timezone.now()
    today = timezone.localdate(now)
    s = subject("Edge")
    # Just inside: the first day of a 7-day window (today - 6).
    inside = make_incident(acme, created_at=now - timedelta(days=6), subject=s)
    # Just outside: one day before the window opens (today - 7).
    outside = make_incident(acme, created_at=now - timedelta(days=7), subject=s)

    result = compute_incident_trend(Incident.objects.all(), days=7, now=now)

    # Only the in-window incident is counted.
    total = sum(c for b in result["buckets"] for c in b["counts"].values())
    assert total == 1
    first_bucket = result["buckets"][0]
    assert first_bucket["date"] == (today - timedelta(days=6)).isoformat()
    assert first_bucket["counts"].get(str(s.id)) == 1


# ── endpoint: scope, tabs, filters, days ─────────────────────────────────────

def _totals(payload):
    return sum(c for b in payload["buckets"] for c in b["counts"].values())


@pytest.mark.django_db
def test_endpoint_tenant_scope_member_only_sees_own_org(client, member, acme, contoso):
    make_incident(acme, subject=subject("A"))
    make_incident(contoso, subject=subject("B"))
    client.force_login(member)
    r = client.get("/api/incidents/trend/")
    assert r.status_code == 200
    # Member sees only their org's single incident.
    assert _totals(r.json()) == 1


@pytest.mark.django_db
def test_endpoint_staff_org_filter(client, staff, acme, contoso):
    make_incident(acme)
    make_incident(contoso)
    make_incident(contoso)
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?org=contoso")
    assert _totals(r.json()) == 2


@pytest.mark.django_db
def test_endpoint_all_orgs_aggregates_tenants_excluding_infra(client, staff, acme, contoso, infra):
    make_incident(acme)
    make_incident(contoso)
    make_incident(infra)  # Infrastructure pseudo-org excluded from all-orgs (ADR-0017)
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?org=__all__")
    assert r.status_code == 200
    assert _totals(r.json()) == 2


@pytest.mark.django_db
def test_endpoint_all_orgs_forbidden_for_non_staff(client, member, acme):
    make_incident(acme)
    client.force_login(member)
    r = client.get("/api/incidents/trend/?org=__all__")
    assert r.status_code == 403


@pytest.mark.django_db
def test_endpoint_honours_unassigned_tab(client, staff, acme):
    make_incident(acme, assignee=None)
    make_incident(acme, assignee=staff)
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?tab=unassigned")
    assert _totals(r.json()) == 1


@pytest.mark.django_db
def test_endpoint_honours_severity_filter(client, staff, acme):
    make_incident(acme, severity="high")
    make_incident(acme, severity="low")
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?severity=high")
    assert _totals(r.json()) == 1


@pytest.mark.django_db
def test_endpoint_honours_closure_reason_filter(client, staff, acme):
    # #628: the trend honours closure_reason just like the list. closure_reason is
    # only set on closed incidents, so pin state=closed to expose both.
    make_incident(acme, state="closed", closure_reason="false_positive")
    make_incident(acme, state="closed", closure_reason="resolved")
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?state=closed&closure_reason=false_positive")
    assert _totals(r.json()) == 1


@pytest.mark.django_db
def test_endpoint_ignores_its_own_subject_param(client, staff, acme):
    s1 = subject("Phishing")
    s2 = subject("Malware")
    make_incident(acme, subject=s1)
    make_incident(acme, subject=s2)
    client.force_login(staff)
    # Even with subject=<id>, the chart shows the full breakdown (both subjects).
    r = client.get(f"/api/incidents/trend/?subject={s1.id}")
    payload = r.json()
    assert _totals(payload) == 2
    real_ids = {s["subject_id"] for s in payload["subjects"] if s["kind"] == "real"}
    assert real_ids == {s1.id, s2.id}


@pytest.mark.django_db
def test_endpoint_ignores_created_within_keeps_full_window(client, staff, acme):
    now = timezone.now()
    make_incident(acme, created_at=now)
    make_incident(acme, created_at=now - timedelta(days=20))
    client.force_login(staff)
    # created_within=24h would drop the older one on the list, but the chart
    # owns the time dimension and shows the full 30-day window.
    r = client.get("/api/incidents/trend/?created_within=24h")
    assert _totals(r.json()) == 2


@pytest.mark.django_db
@pytest.mark.parametrize("param,expected", [
    ("", 30), ("7", 7), ("30", 30), ("90", 90),
    ("15", 30), ("abc", 30), ("0", 30),
])
def test_endpoint_days_validation(client, staff, acme, param, expected):
    client.force_login(staff)
    url = "/api/incidents/trend/" + (f"?days={param}" if param else "")
    r = client.get(url)
    assert r.status_code == 200
    payload = r.json()
    assert payload["days"] == expected
    assert len(payload["buckets"]) == expected


@pytest.mark.django_db
def test_endpoint_response_shape(client, staff, acme):
    make_incident(acme, subject=subject("Recon"))
    client.force_login(staff)
    r = client.get("/api/incidents/trend/?days=7")
    payload = r.json()
    assert set(payload) == {"days", "start", "end", "buckets", "subjects"}
    assert all(set(b) == {"date", "counts"} for b in payload["buckets"])
    assert all({"key", "subject_id", "name", "kind"} <= set(s) for s in payload["subjects"])


# ── shared queryset builder parity ───────────────────────────────────────────

@pytest.mark.django_db
def test_builder_excludes_closed_by_default(member, acme):
    make_incident(acme, state="new")
    make_incident(acme, state="closed")
    from django.http import QueryDict
    qs = build_incident_queryset(member, QueryDict(""))
    assert qs.count() == 1


@pytest.mark.django_db
def test_builder_include_closed_keeps_closed(member, acme):
    make_incident(acme, state="new")
    make_incident(acme, state="closed")
    from django.http import QueryDict
    qs = build_incident_queryset(member, QueryDict("include_closed=1"))
    assert qs.count() == 2


@pytest.mark.django_db
def test_endpoint_include_closed_counts_all_states(client, staff, acme):
    # The dashboard trend passes include_closed=1 so it reflects every incident
    # regardless of state; without it the closed one is dropped (default rule).
    make_incident(acme, state="new")
    make_incident(acme, state="closed")
    client.force_login(staff)
    assert _totals(client.get("/api/incidents/trend/").json()) == 1
    assert _totals(client.get("/api/incidents/trend/?include_closed=1").json()) == 2
