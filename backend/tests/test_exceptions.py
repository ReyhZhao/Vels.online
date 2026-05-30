import pytest
from unittest.mock import patch

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


# ── _is_placeholder unit tests ────────────────────────────────────────────────


def test_is_placeholder_angle_brackets():
    from exceptions.views import _is_placeholder
    assert _is_placeholder("<match_value>") is True
    assert _is_placeholder("real value") is False


def test_is_placeholder_square_brackets():
    from exceptions.views import _is_placeholder
    assert _is_placeholder("[YOUR_VALUE]") is True
    assert _is_placeholder("10.0.0.1") is False


def test_is_placeholder_all_caps_underscore():
    from exceptions.views import _is_placeholder
    assert _is_placeholder("YOUR_VALUE_HERE") is True
    assert _is_placeholder("MATCH_VALUE") is True
    assert _is_placeholder("SomeRealValue") is False


def test_is_placeholder_empty_string_is_not_placeholder():
    from exceptions.views import _is_placeholder
    assert _is_placeholder("") is False


# ── POST /api/exceptions/ validation ─────────────────────────────────────────

VALID_POST_PAYLOAD = {
    "org": "acme",
    "trigger_rule_id": 100200,
    "description": "Suppress expected cron noise on agent1",
    "match_value": "",
    "field_name": "",
    "field_value": "",
    "field_type": "literal",
    "scope": "org",
    "agent_name": "",
}


@pytest.mark.django_db
def test_create_exception_missing_trigger_rule_id(admin_client, acme, pool):
    payload = {**VALID_POST_PAYLOAD, "trigger_rule_id": None}
    res = admin_client.post("/api/exceptions/", payload, content_type="application/json")
    assert res.status_code == 400
    assert "trigger_rule_id" in res.json()["detail"]


@pytest.mark.django_db
def test_create_exception_empty_description(admin_client, acme, pool):
    payload = {**VALID_POST_PAYLOAD, "description": "   "}
    res = admin_client.post("/api/exceptions/", payload, content_type="application/json")
    assert res.status_code == 400
    assert "description" in res.json()["detail"]


@pytest.mark.django_db
def test_create_exception_angle_bracket_placeholder(admin_client, acme, pool):
    payload = {**VALID_POST_PAYLOAD, "match_value": "<match_value>"}
    res = admin_client.post("/api/exceptions/", payload, content_type="application/json")
    assert res.status_code == 400
    assert "match_value" in res.json()["detail"]


@pytest.mark.django_db
def test_create_exception_square_bracket_placeholder(admin_client, acme, pool):
    payload = {**VALID_POST_PAYLOAD, "field_name": "[FIELD_NAME]"}
    res = admin_client.post("/api/exceptions/", payload, content_type="application/json")
    assert res.status_code == 400
    assert "field_name" in res.json()["detail"]


@pytest.mark.django_db
def test_create_exception_all_caps_placeholder(admin_client, acme, pool):
    payload = {**VALID_POST_PAYLOAD, "agent_name": "YOUR_AGENT_NAME"}
    res = admin_client.post("/api/exceptions/", payload, content_type="application/json")
    assert res.status_code == 400
    assert "agent_name" in res.json()["detail"]


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_create_exception_valid_payload_succeeds(mock_push, admin_client, acme, pool):
    mock_push.return_value = None
    res = admin_client.post("/api/exceptions/", VALID_POST_PAYLOAD, content_type="application/json")
    assert res.status_code == 201
    data = res.json()
    assert data["trigger_rule_id"] == 100200
    assert data["description"] == "Suppress expected cron noise on agent1"


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_create_exception_github_push_failure_returns_502(mock_push, admin_client, acme, pool):
    mock_push.side_effect = Exception("404 Not Found")
    res = admin_client.post("/api/exceptions/", VALID_POST_PAYLOAD, content_type="application/json")
    assert res.status_code == 502
    assert "detail" in res.json()


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_create_exception_github_push_failure_rolls_back_db(mock_push, admin_client, acme, pool):
    mock_push.side_effect = Exception("404 Not Found")
    admin_client.post("/api/exceptions/", VALID_POST_PAYLOAD, content_type="application/json")
    assert ExceptionRule.objects.count() == 0


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_create_exception_github_push_failure_frees_rule_id(mock_push, admin_client, acme, pool):
    mock_push.side_effect = Exception("404 Not Found")
    admin_client.post("/api/exceptions/", VALID_POST_PAYLOAD, content_type="application/json")
    # After rollback the ID is freed; the next allocation should reuse it
    assert allocate_rule_id() == 200000


# ── POST /api/exceptions/<id>/approve/ ───────────────────────────────────────


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_approve_github_push_failure_returns_502(mock_push, admin_client, acme):
    rule = make_rule(acme, status="pending")
    mock_push.side_effect = Exception("502 Bad Gateway")
    res = admin_client.post(f"/api/exceptions/{rule.id}/approve/")
    assert res.status_code == 502
    assert "detail" in res.json()


@pytest.mark.django_db
@patch("exceptions.views.push_rule")
def test_approve_github_push_failure_leaves_rule_pending(mock_push, admin_client, acme):
    rule = make_rule(acme, status="pending")
    mock_push.side_effect = Exception("502 Bad Gateway")
    admin_client.post(f"/api/exceptions/{rule.id}/approve/")
    rule.refresh_from_db()
    assert rule.status == "pending"


# ── POST /api/exceptions/<id>/disable/ ───────────────────────────────────────


@pytest.mark.django_db
@patch("exceptions.views.remove_rule")
def test_disable_github_remove_failure_returns_502(mock_remove, admin_client, acme):
    rule = make_rule(acme, status="applied")
    mock_remove.side_effect = Exception("500 Server Error")
    res = admin_client.post(f"/api/exceptions/{rule.id}/disable/")
    assert res.status_code == 502
    assert "detail" in res.json()


@pytest.mark.django_db
@patch("exceptions.views.remove_rule")
def test_disable_github_remove_failure_leaves_rule_applied(mock_remove, admin_client, acme):
    rule = make_rule(acme, status="applied")
    mock_remove.side_effect = Exception("500 Server Error")
    admin_client.post(f"/api/exceptions/{rule.id}/disable/")
    rule.refresh_from_db()
    assert rule.status == "applied"


@pytest.mark.django_db
@patch("exceptions.views.remove_rule")
def test_disable_github_remove_failure_does_not_free_rule_id(mock_remove, admin_client, acme, pool):
    rule = make_rule(acme, status="applied")
    rule.wazuh_rule_id = 200001
    rule.save()
    mock_remove.side_effect = Exception("500 Server Error")
    admin_client.post(f"/api/exceptions/{rule.id}/disable/")
    # ID should NOT have been freed — FreedRuleId table should be empty
    assert FreedRuleId.objects.filter(rule_id=200001).count() == 0
