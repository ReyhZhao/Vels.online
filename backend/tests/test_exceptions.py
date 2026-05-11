import pytest
from security.models import Organization, OrganizationMembership
from exceptions.models import ExceptionRule, FreedRuleId, WazuhRuleIdPool
from exceptions.services import allocate_rule_id, free_rule_id


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def pool(db):
    obj, _ = WazuhRuleIdPool.objects.get_or_create(defaults={"last_assigned_id": 199999})
    obj.last_assigned_id = 199999
    obj.save()
    return obj


def make_rule(org, status="pending", description="Test rule"):
    return ExceptionRule.objects.create(
        organisation=org, status=status, description=description
    )


# ── ID allocation service ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_first_allocation_returns_200000(pool):
    assert allocate_rule_id() == 200000


@pytest.mark.django_db
def test_sequential_allocation(pool):
    assert allocate_rule_id() == 200000
    assert allocate_rule_id() == 200001
    assert allocate_rule_id() == 200002


@pytest.mark.django_db
def test_freed_id_returned_before_counter_increments(pool):
    allocate_rule_id()  # 200000
    allocate_rule_id()  # 200001
    free_rule_id(200000)
    assert allocate_rule_id() == 200000  # reused
    assert allocate_rule_id() == 200002  # counter resumes


@pytest.mark.django_db
def test_pool_exhaustion_raises(pool):
    pool.last_assigned_id = WazuhRuleIdPool.POOL_MAX
    pool.save()
    with pytest.raises(ValueError, match="exhausted"):
        allocate_rule_id()


@pytest.mark.django_db
def test_freed_id_bypasses_exhausted_counter(pool):
    pool.last_assigned_id = WazuhRuleIdPool.POOL_MAX
    pool.save()
    FreedRuleId.objects.create(rule_id=200050)
    assert allocate_rule_id() == 200050


# ── GET /api/exceptions/ ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client, acme):
    response = client.get("/api/exceptions/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_list_org_member_sees_own_org_only(client, acme_member, acme, contoso):
    own = make_rule(acme)
    other = make_rule(contoso)
    client.force_login(acme_member)
    response = client.get("/api/exceptions/")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert own.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_list_staff_sees_all(admin_client, acme, contoso):
    r1 = make_rule(acme)
    r2 = make_rule(contoso)
    response = admin_client.get("/api/exceptions/")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert r1.id in ids
    assert r2.id in ids


@pytest.mark.django_db
def test_list_filter_by_status(admin_client, acme):
    pending = make_rule(acme, status="pending")
    applied = make_rule(acme, status="applied")
    response = admin_client.get("/api/exceptions/?status=pending")
    ids = [r["id"] for r in response.json()]
    assert pending.id in ids
    assert applied.id not in ids


@pytest.mark.django_db
def test_list_filter_by_organisation(admin_client, acme, contoso):
    r1 = make_rule(acme)
    r2 = make_rule(contoso)
    response = admin_client.get("/api/exceptions/?organisation=acme")
    ids = [r["id"] for r in response.json()]
    assert r1.id in ids
    assert r2.id not in ids


# ── GET /api/exceptions/<id>/ ────────────────────────────────────────────────


@pytest.mark.django_db
def test_detail_requires_auth(client, acme):
    rule = make_rule(acme)
    assert client.get(f"/api/exceptions/{rule.id}/").status_code == 401


@pytest.mark.django_db
def test_detail_org_member_can_view_own_rule(client, acme_member, acme):
    rule = make_rule(acme)
    client.force_login(acme_member)
    response = client.get(f"/api/exceptions/{rule.id}/")
    assert response.status_code == 200
    assert response.json()["id"] == rule.id


@pytest.mark.django_db
def test_detail_org_member_cannot_view_other_org_rule(client, acme_member, contoso):
    rule = make_rule(contoso)
    client.force_login(acme_member)
    response = client.get(f"/api/exceptions/{rule.id}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_staff_can_view_any_rule(admin_client, contoso):
    rule = make_rule(contoso)
    response = admin_client.get(f"/api/exceptions/{rule.id}/")
    assert response.status_code == 200
