"""
Backend tests for the 8-filter incident list endpoint (issue #110).
"""
import pytest
from django.utils import timezone

from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentDelegation, Subject
from incidents.services.delegation import delegate


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture
def staff2(db, django_user_model):
    return django_user_model.objects.create_user(username="staff2", password="p", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="p")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


_counter = [0]


def make_incident(org, **kwargs):
    _counter[0] += 1
    defaults = dict(
        title="Test",
        display_id=f"INC-{_counter[0]:04d}",
        severity="medium",
        tlp="amber",
        state="new",
    )
    defaults.update(kwargs)
    return Incident.objects.create(organization=org, **defaults)


def ids(response):
    return [i["id"] for i in response.json()["results"]]


# ── response shape ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_response_includes_pagination_metadata(client, staff, acme):
    client.force_login(staff)
    make_incident(acme)
    r = client.get("/api/incidents/")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "page" in data
    assert "per_page" in data
    assert "total_pages" in data
    assert "results" in data


@pytest.mark.django_db
def test_per_page_default_25(client, staff, acme):
    client.force_login(staff)
    for _ in range(30):
        make_incident(acme)
    r = client.get("/api/incidents/")
    data = r.json()
    assert data["per_page"] == 25
    assert len(data["results"]) == 25


@pytest.mark.django_db
def test_per_page_custom(client, staff, acme):
    client.force_login(staff)
    for _ in range(10):
        make_incident(acme)
    r = client.get("/api/incidents/?per_page=5")
    data = r.json()
    assert data["per_page"] == 5
    assert len(data["results"]) == 5


@pytest.mark.django_db
def test_per_page_capped_at_100(client, staff, acme):
    client.force_login(staff)
    r = client.get("/api/incidents/?per_page=500")
    assert r.json()["per_page"] == 100


@pytest.mark.django_db
def test_pagination_second_page(client, staff, acme):
    client.force_login(staff)
    for _ in range(30):
        make_incident(acme)
    r1 = client.get("/api/incidents/?per_page=25&page=1")
    r2 = client.get("/api/incidents/?per_page=25&page=2")
    assert len(r1.json()["results"]) == 25
    assert len(r2.json()["results"]) == 5
    ids1 = {i["id"] for i in r1.json()["results"]}
    ids2 = {i["id"] for i in r2.json()["results"]}
    assert ids1.isdisjoint(ids2)


# ── default sort ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_default_sort_severity_desc_then_created_at_asc(client, staff, acme):
    low = make_incident(acme, severity="low", state="in_progress")
    critical = make_incident(acme, severity="critical", state="in_progress")
    high = make_incident(acme, severity="high", state="in_progress")
    medium = make_incident(acme, severity="medium", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/")
    result_ids = [i["id"] for i in r.json()["results"]]
    # critical first, then high, then medium, then low
    assert result_ids.index(critical.id) < result_ids.index(high.id)
    assert result_ids.index(high.id) < result_ids.index(medium.id)
    assert result_ids.index(medium.id) < result_ids.index(low.id)


# ── state filter ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_state_filter_single(client, staff, acme):
    make_incident(acme, state="new")
    make_incident(acme, state="in_progress")
    make_incident(acme, state="resolved")
    client.force_login(staff)
    r = client.get("/api/incidents/?state=new")
    assert all(i["state"] == "new" for i in r.json()["results"])


@pytest.mark.django_db
def test_state_filter_multi_comma(client, staff, acme):
    new = make_incident(acme, state="new")
    ip = make_incident(acme, state="in_progress")
    make_incident(acme, state="resolved")
    client.force_login(staff)
    r = client.get("/api/incidents/?state=new,in_progress")
    result_ids = ids(r)
    assert new.id in result_ids
    assert ip.id in result_ids
    assert all(i["state"] in ("new", "in_progress") for i in r.json()["results"])


@pytest.mark.django_db
def test_state_filter_multi_repeated_param(client, staff, acme):
    new = make_incident(acme, state="new")
    ip = make_incident(acme, state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?state=new&state=in_progress")
    result_ids = ids(r)
    assert new.id in result_ids
    assert ip.id in result_ids


@pytest.mark.django_db
def test_default_excludes_closed(client, staff, acme):
    open_inc = make_incident(acme, state="new")
    closed_inc = make_incident(acme, state="closed")
    client.force_login(staff)
    r = client.get("/api/incidents/")
    result_ids = ids(r)
    assert open_inc.id in result_ids
    assert closed_inc.id not in result_ids


# ── severity filter ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_severity_filter(client, staff, acme):
    high = make_incident(acme, severity="high", state="in_progress")
    make_incident(acme, severity="low", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?severity=high")
    result_ids = ids(r)
    assert high.id in result_ids
    assert all(i["severity"] == "high" for i in r.json()["results"])


@pytest.mark.django_db
def test_severity_filter_multi(client, staff, acme):
    critical = make_incident(acme, severity="critical", state="in_progress")
    high = make_incident(acme, severity="high", state="in_progress")
    make_incident(acme, severity="medium", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?severity=critical,high")
    result_ids = ids(r)
    assert critical.id in result_ids
    assert high.id in result_ids


# ── org filter ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_org_filter(client, staff, acme, contoso):
    acme_inc = make_incident(acme, state="in_progress")
    contoso_inc = make_incident(contoso, state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?org=acme")
    result_ids = ids(r)
    assert acme_inc.id in result_ids
    assert contoso_inc.id not in result_ids


# ── assignee filter ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_assignee_me(client, staff, acme):
    mine = make_incident(acme, state="in_progress", assignee=staff)
    other = make_incident(acme, state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?assignee=me")
    result_ids = ids(r)
    assert mine.id in result_ids
    assert other.id not in result_ids


@pytest.mark.django_db
def test_assignee_unassigned(client, staff, acme, staff2):
    unassigned = make_incident(acme, state="in_progress")
    assigned = make_incident(acme, state="in_progress", assignee=staff)
    client.force_login(staff)
    r = client.get("/api/incidents/?assignee=unassigned")
    result_ids = ids(r)
    assert unassigned.id in result_ids
    assert assigned.id not in result_ids


@pytest.mark.django_db
def test_assignee_specific_user_id(client, staff, staff2, acme):
    theirs = make_incident(acme, state="in_progress", assignee=staff2)
    mine = make_incident(acme, state="in_progress", assignee=staff)
    client.force_login(staff)
    r = client.get(f"/api/incidents/?assignee={staff2.id}")
    result_ids = ids(r)
    assert theirs.id in result_ids
    assert mine.id not in result_ids


# ── TLP filter ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_tlp_filter_multi(client, staff, acme):
    amber = make_incident(acme, tlp="amber", state="in_progress")
    green = make_incident(acme, tlp="green", state="in_progress")
    red = make_incident(acme, tlp="red", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?tlp=amber,green")
    result_ids = ids(r)
    assert amber.id in result_ids
    assert green.id in result_ids
    assert red.id not in result_ids


# ── free-text filter ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_q_matches_title(client, staff, acme):
    match = make_incident(acme, title="Ransomware attack", state="in_progress")
    no_match = make_incident(acme, title="Normal patching", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?q=ransomware")
    result_ids = ids(r)
    assert match.id in result_ids
    assert no_match.id not in result_ids


@pytest.mark.django_db
def test_q_matches_description(client, staff, acme):
    match = make_incident(acme, description="phishing campaign", state="in_progress")
    no_match = make_incident(acme, description="routine maintenance", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?q=phishing")
    result_ids = ids(r)
    assert match.id in result_ids
    assert no_match.id not in result_ids


@pytest.mark.django_db
def test_q_matches_display_id(client, staff, acme):
    _counter[0] += 1
    inc = Incident.objects.create(
        organization=acme, title="x", display_id="INC-FIND-ME", severity="low"
    )
    client.force_login(staff)
    r = client.get("/api/incidents/?q=FIND-ME&state=new,in_progress,triaged,on_hold,resolved,closed")
    result_ids = ids(r)
    assert inc.id in result_ids


# ── created_within filter ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_created_within_hours(client, staff, acme):
    from django.utils import timezone
    from datetime import timedelta

    recent = make_incident(acme, state="in_progress")
    old = make_incident(acme, state="in_progress")
    # Backdate the old incident
    Incident.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))

    client.force_login(staff)
    r = client.get("/api/incidents/?created_within=24h")
    result_ids = ids(r)
    assert recent.id in result_ids
    assert old.id not in result_ids


@pytest.mark.django_db
def test_created_within_days(client, staff, acme):
    from django.utils import timezone
    from datetime import timedelta

    recent = make_incident(acme, state="in_progress")
    old = make_incident(acme, state="in_progress")
    Incident.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))

    client.force_login(staff)
    r = client.get("/api/incidents/?created_within=7d")
    result_ids = ids(r)
    assert recent.id in result_ids
    assert old.id not in result_ids


# ── tab filters ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_tab_my_queue_returns_my_assigned(client, staff, staff2, acme):
    mine = make_incident(acme, state="in_progress", assignee=staff)
    other = make_incident(acme, state="in_progress", assignee=staff2)
    client.force_login(staff)
    r = client.get("/api/incidents/?tab=my_queue")
    result_ids = ids(r)
    assert mine.id in result_ids
    assert other.id not in result_ids


@pytest.mark.django_db
def test_tab_my_queue_includes_active_delegations(client, staff, staff2, acme):
    incident = make_incident(acme, state="in_progress", assignee=staff2)
    client.force_login(staff2)
    # Delegate to staff
    IncidentDelegation.objects.create(
        incident=incident, user=staff, delegated_by=staff2
    )
    client.force_login(staff)
    r = client.get("/api/incidents/?tab=my_queue")
    result_ids = ids(r)
    assert incident.id in result_ids


@pytest.mark.django_db
def test_tab_my_queue_excludes_closed_by_default(client, staff, acme):
    open_mine = make_incident(acme, state="in_progress", assignee=staff)
    closed_mine = make_incident(acme, state="closed", assignee=staff)
    client.force_login(staff)
    r = client.get("/api/incidents/?tab=my_queue")
    result_ids = ids(r)
    assert open_mine.id in result_ids
    assert closed_mine.id not in result_ids


@pytest.mark.django_db
def test_tab_unassigned(client, staff, acme, staff2):
    unassigned = make_incident(acme, state="in_progress")
    assigned = make_incident(acme, state="in_progress", assignee=staff)
    client.force_login(staff)
    r = client.get("/api/incidents/?tab=unassigned")
    result_ids = ids(r)
    assert unassigned.id in result_ids
    assert assigned.id not in result_ids


# ── sort param ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sort_by_title_asc(client, staff, acme):
    b = make_incident(acme, title="Beta", state="in_progress")
    a = make_incident(acme, title="Alpha", state="in_progress")
    c = make_incident(acme, title="Gamma", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=title&order=asc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(a.id) < result_ids.index(b.id) < result_ids.index(c.id)


@pytest.mark.django_db
def test_sort_by_title_desc(client, staff, acme):
    b = make_incident(acme, title="Beta", state="in_progress")
    a = make_incident(acme, title="Alpha", state="in_progress")
    c = make_incident(acme, title="Gamma", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=title&order=desc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(c.id) < result_ids.index(b.id) < result_ids.index(a.id)


@pytest.mark.django_db
def test_sort_by_severity_desc(client, staff, acme):
    low = make_incident(acme, severity="low", state="in_progress")
    critical = make_incident(acme, severity="critical", state="in_progress")
    high = make_incident(acme, severity="high", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=severity&order=desc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(critical.id) < result_ids.index(high.id)
    assert result_ids.index(high.id) < result_ids.index(low.id)


@pytest.mark.django_db
def test_sort_by_severity_asc(client, staff, acme):
    low = make_incident(acme, severity="low", state="in_progress")
    critical = make_incident(acme, severity="critical", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=severity&order=asc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(low.id) < result_ids.index(critical.id)


@pytest.mark.django_db
def test_sort_by_created_at_asc(client, staff, acme):
    from datetime import timedelta
    from django.utils import timezone

    newer = make_incident(acme, state="in_progress")
    older = make_incident(acme, state="in_progress")
    Incident.objects.filter(pk=older.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=created_at&order=asc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(older.id) < result_ids.index(newer.id)


@pytest.mark.django_db
def test_sort_by_assignee_asc_nulls_last(client, staff, staff2, acme):
    unassigned = make_incident(acme, state="in_progress")
    assigned = make_incident(acme, state="in_progress", assignee=staff2)
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=assignee&order=asc&state=in_progress")
    result_ids = ids(r)
    assert result_ids.index(assigned.id) < result_ids.index(unassigned.id)


@pytest.mark.django_db
def test_unknown_sort_falls_back_to_default(client, staff, acme):
    low = make_incident(acme, severity="low", state="in_progress")
    critical = make_incident(acme, severity="critical", state="in_progress")
    client.force_login(staff)
    r = client.get("/api/incidents/?sort=bogus&state=in_progress")
    result_ids = ids(r)
    # Default is severity desc — critical before low
    assert result_ids.index(critical.id) < result_ids.index(low.id)


# ── subject filter (drill-down) ───────────────────────────────────────────────

@pytest.mark.django_db
def test_subject_filter_numeric_matches_that_subject(client, staff, acme):
    bf = Subject.objects.create(name="Brute Force", slug="bf-test")
    matched = make_incident(acme, state="in_progress", subject=bf)
    other = make_incident(acme, state="in_progress")
    client.force_login(staff)
    r = client.get(f"/api/incidents/?subject={bf.id}")
    result_ids = ids(r)
    assert matched.id in result_ids
    assert other.id not in result_ids


@pytest.mark.django_db
def test_subject_filter_none_matches_unclassified(client, staff, acme):
    bf = Subject.objects.create(name="Brute Force", slug="bf-test2")
    classified = make_incident(acme, state="in_progress", subject=bf)
    unclassified = make_incident(acme, state="in_progress", subject=None)
    client.force_login(staff)
    r = client.get("/api/incidents/?subject=none")
    result_ids = ids(r)
    assert unclassified.id in result_ids
    assert classified.id not in result_ids


# ── combinations ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_severity_and_state_combination(client, staff, acme):
    match = make_incident(acme, severity="high", state="in_progress")
    wrong_sev = make_incident(acme, severity="low", state="in_progress")
    wrong_state = make_incident(acme, severity="high", state="resolved")
    client.force_login(staff)
    r = client.get("/api/incidents/?severity=high&state=in_progress")
    result_ids = ids(r)
    assert match.id in result_ids
    assert wrong_sev.id not in result_ids
    assert wrong_state.id not in result_ids
