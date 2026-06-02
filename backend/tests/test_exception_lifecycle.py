import pytest
from unittest.mock import patch

from security.models import Organization, OrganizationMembership
from exceptions.models import ExceptionRule, WazuhRuleIdPool, FreedRuleId


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


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


@pytest.fixture
def pending_rule(db, acme):
    return ExceptionRule.objects.create(
        wazuh_rule_id=200001,
        description="Test rule",
        scope="org",
        organisation=acme,
        status="pending",
    )


@pytest.fixture
def applied_rule(db, acme):
    return ExceptionRule.objects.create(
        wazuh_rule_id=200002,
        description="Applied rule",
        scope="org",
        organisation=acme,
        status="applied",
    )


# ── PATCH /api/exceptions/<id>/ ───────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_requires_staff(client, acme_member, pending_rule):
    client.force_login(acme_member)
    response = client.patch(
        f"/api/exceptions/{pending_rule.pk}/",
        {"description": "Updated"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_updates_description(admin_client, pending_rule):
    response = admin_client.patch(
        f"/api/exceptions/{pending_rule.pk}/",
        {"description": "Updated description"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"
    pending_rule.refresh_from_db()
    assert pending_rule.description == "Updated description"


@pytest.mark.django_db
def test_patch_applied_rule_resets_to_pending(admin_client, applied_rule):
    response = admin_client.patch(
        f"/api/exceptions/{applied_rule.pk}/",
        {"description": "Changed"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    applied_rule.refresh_from_db()
    assert applied_rule.status == "pending"


@pytest.mark.django_db
def test_patch_pending_rule_stays_pending(admin_client, pending_rule):
    response = admin_client.patch(
        f"/api/exceptions/{pending_rule.pk}/",
        {"description": "Changed"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.django_db
def test_patch_nonexistent_returns_404(admin_client):
    response = admin_client.patch(
        "/api/exceptions/99999/",
        {"description": "x"},
        content_type="application/json",
    )
    assert response.status_code == 404


# ── POST /api/exceptions/<id>/approve/ ───────────────────────────────────────


@pytest.mark.django_db
def test_approve_requires_staff(client, acme_member, pending_rule):
    client.force_login(acme_member)
    response = client.post(f"/api/exceptions/{pending_rule.pk}/approve/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_approve_pending_rule(admin_client, pending_rule):
    with patch("exceptions.views.push_rule") as mock_push:
        response = admin_client.post(f"/api/exceptions/{pending_rule.pk}/approve/")
    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    mock_push.assert_called_once()
    pending_rule.refresh_from_db()
    assert pending_rule.status == "applied"


@pytest.mark.django_db
def test_approve_already_applied_returns_400(admin_client, applied_rule):
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(f"/api/exceptions/{applied_rule.pk}/approve/")
    assert response.status_code == 400
    assert "pending" in response.json()["detail"]


@pytest.mark.django_db
def test_approve_push_failure_returns_502_and_leaves_pending(admin_client, pending_rule):
    with patch("exceptions.views.push_rule", side_effect=RuntimeError("network")):
        response = admin_client.post(f"/api/exceptions/{pending_rule.pk}/approve/")
    assert response.status_code == 502
    pending_rule.refresh_from_db()
    assert pending_rule.status == "pending"


@pytest.mark.django_db
def test_approve_nonexistent_returns_404(admin_client):
    response = admin_client.post("/api/exceptions/99999/approve/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_approve_schedules_manager_restart(admin_client, pending_rule):
    with patch("exceptions.views.push_rule"), \
         patch("exceptions.views.restart_wazuh_manager") as mock_task:
        admin_client.post(f"/api/exceptions/{pending_rule.pk}/approve/")
    mock_task.apply_async.assert_called_once()


@pytest.mark.django_db
def test_create_schedules_manager_restart(admin_client, pool, acme):
    with patch("exceptions.views.push_rule"), \
         patch("exceptions.views.restart_wazuh_manager") as mock_task:
        admin_client.post(
            "/api/exceptions/",
            {
                "org": acme.slug,
                "description": "Block noisy rule",
                "trigger_rule_id": 100001,
                "scope": "org",
            },
            content_type="application/json",
        )
    mock_task.apply_async.assert_called_once()


# ── POST /api/exceptions/<id>/disable/ ───────────────────────────────────────


@pytest.mark.django_db
def test_disable_requires_staff(client, acme_member, applied_rule):
    client.force_login(acme_member)
    response = client.post(f"/api/exceptions/{applied_rule.pk}/disable/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_disable_applied_rule(admin_client, applied_rule, pool):
    with patch("exceptions.views.remove_rule") as mock_remove:
        response = admin_client.post(f"/api/exceptions/{applied_rule.pk}/disable/")
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    mock_remove.assert_called_once()
    applied_rule.refresh_from_db()
    assert applied_rule.status == "disabled"


@pytest.mark.django_db
def test_disable_frees_rule_id(admin_client, applied_rule, pool):
    rule_id = applied_rule.wazuh_rule_id
    with patch("exceptions.views.remove_rule"):
        admin_client.post(f"/api/exceptions/{applied_rule.pk}/disable/")
    assert FreedRuleId.objects.filter(rule_id=rule_id).exists()


@pytest.mark.django_db
def test_disable_pending_rule_returns_400(admin_client, pending_rule):
    with patch("exceptions.views.remove_rule"):
        response = admin_client.post(f"/api/exceptions/{pending_rule.pk}/disable/")
    assert response.status_code == 400
    assert "applied" in response.json()["detail"]


@pytest.mark.django_db
def test_disable_remove_failure_returns_502_and_leaves_applied(admin_client, applied_rule, pool):
    with patch("exceptions.views.remove_rule", side_effect=RuntimeError("network")):
        response = admin_client.post(f"/api/exceptions/{applied_rule.pk}/disable/")
    assert response.status_code == 502
    applied_rule.refresh_from_db()
    assert applied_rule.status == "applied"


@pytest.mark.django_db
def test_disable_nonexistent_returns_404(admin_client):
    response = admin_client.post("/api/exceptions/99999/disable/")
    assert response.status_code == 404
