"""Tests for correlation rule CRUD API."""
import pytest
from security.models import Organization
from correlations.models import (
    CorrelationRule,
    CorrelationRuleLeg,
    LegCondition,
)


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="staff_cr", password="pass", is_staff=True
    )


@pytest.fixture
def non_staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="user_cr", password="pass", is_staff=False
    )


@pytest.fixture
def rule(db):
    r = CorrelationRule.objects.create(
        name="Port Scan Rule",
        correlation_key="source.ip",
        window_minutes=30,
        severity="high",
        enabled=True,
    )
    leg = CorrelationRuleLeg.objects.create(rule=r, count=2, display_order=0)
    LegCondition.objects.create(
        leg=leg,
        field_kind="alert_field",
        field_name="severity",
        operator="equals",
        value="high",
    )
    return r


VALID_PAYLOAD = {
    "name": "Brute Force Rule",
    "description": "Detects brute force",
    "correlation_key": "source.ip",
    "window_minutes": 60,
    "severity": "high",
    "enabled": True,
    "legs": [
        {
            "count": 3,
            "display_order": 0,
            "conditions": [
                {
                    "field_kind": "alert_field",
                    "field_name": "title",
                    "operator": "contains",
                    "value": "login failed",
                }
            ],
        }
    ],
}


# ── GET /api/correlations/rules/ ─────────────────────────────────────────────

@pytest.mark.django_db
def test_list_rules_requires_auth(client):
    r = client.get("/api/correlations/rules/")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_list_rules_requires_staff(client, non_staff):
    client.force_login(non_staff)
    r = client.get("/api/correlations/rules/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_list_rules_returns_rules(client, staff, rule):
    client.force_login(staff)
    r = client.get("/api/correlations/rules/")
    assert r.status_code == 200
    names = [x["name"] for x in r.json()]
    assert "Port Scan Rule" in names


@pytest.mark.django_db
def test_list_rules_includes_legs(client, staff, rule):
    client.force_login(staff)
    r = client.get("/api/correlations/rules/")
    data = r.json()
    assert len(data) == 1
    assert len(data[0]["legs"]) == 1
    assert len(data[0]["legs"][0]["conditions"]) == 1


# ── POST /api/correlations/rules/ ────────────────────────────────────────────

@pytest.mark.django_db
def test_create_rule_requires_staff(client, non_staff):
    client.force_login(non_staff)
    r = client.post(
        "/api/correlations/rules/",
        data=VALID_PAYLOAD,
        content_type="application/json",
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_create_rule_success(client, staff):
    client.force_login(staff)
    r = client.post(
        "/api/correlations/rules/",
        data=VALID_PAYLOAD,
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Brute Force Rule"
    assert len(data["legs"]) == 1
    assert data["legs"][0]["count"] == 3
    assert len(data["legs"][0]["conditions"]) == 1


@pytest.mark.django_db
def test_create_rule_invalid_field_name(client, staff):
    payload = {
        **VALID_PAYLOAD,
        "legs": [
            {
                "count": 1,
                "display_order": 0,
                "conditions": [
                    {
                        "field_kind": "alert_field",
                        "field_name": "nonexistent_field",
                        "operator": "equals",
                        "value": "high",
                    }
                ],
            }
        ],
    }
    client.force_login(staff)
    r = client.post(
        "/api/correlations/rules/",
        data=payload,
        content_type="application/json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_create_rule_invalid_operator_for_kind(client, staff):
    payload = {
        **VALID_PAYLOAD,
        "legs": [
            {
                "count": 1,
                "display_order": 0,
                "conditions": [
                    {
                        "field_kind": "source_ref",
                        "field_name": "rule_id",
                        "operator": "cidr",
                        "value": "10.0.0.0/8",
                    }
                ],
            }
        ],
    }
    client.force_login(staff)
    r = client.post(
        "/api/correlations/rules/",
        data=payload,
        content_type="application/json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_create_rule_entity_cidr_allowed(client, staff):
    payload = {
        **VALID_PAYLOAD,
        "legs": [
            {
                "count": 1,
                "display_order": 0,
                "conditions": [
                    {
                        "field_kind": "entity",
                        "field_name": "source.ip",
                        "operator": "cidr",
                        "value": "10.0.0.0/8",
                    }
                ],
            }
        ],
    }
    client.force_login(staff)
    r = client.post(
        "/api/correlations/rules/",
        data=payload,
        content_type="application/json",
    )
    assert r.status_code == 201


# ── PATCH /api/correlations/rules/<pk>/ ──────────────────────────────────────

@pytest.mark.django_db
def test_patch_rule_name(client, staff, rule):
    client.force_login(staff)
    r = client.patch(
        f"/api/correlations/rules/{rule.pk}/",
        data={"name": "Updated Rule"},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Rule"


@pytest.mark.django_db
def test_patch_rule_enable_disable(client, staff, rule):
    client.force_login(staff)
    r = client.patch(
        f"/api/correlations/rules/{rule.pk}/",
        data={"enabled": False},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    rule.refresh_from_db()
    assert rule.enabled is False


@pytest.mark.django_db
def test_patch_rule_replaces_legs(client, staff, rule):
    client.force_login(staff)
    r = client.patch(
        f"/api/correlations/rules/{rule.pk}/",
        data={
            "legs": [
                {
                    "count": 5,
                    "display_order": 0,
                    "conditions": [
                        {
                            "field_kind": "entity",
                            "field_name": "host.name",
                            "operator": "equals",
                            "value": "badhost",
                        }
                    ],
                },
                {
                    "count": 2,
                    "display_order": 1,
                    "conditions": [
                        {
                            "field_kind": "source_ref",
                            "field_name": "rule_id",
                            "operator": "equals",
                            "value": "1234",
                        }
                    ],
                },
            ]
        },
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["legs"]) == 2
    assert data["legs"][0]["count"] == 5


@pytest.mark.django_db
def test_patch_rule_not_found(client, staff):
    client.force_login(staff)
    r = client.patch(
        "/api/correlations/rules/99999/",
        data={"name": "x"},
        content_type="application/json",
    )
    assert r.status_code == 404


# ── DELETE /api/correlations/rules/<pk>/ ─────────────────────────────────────

@pytest.mark.django_db
def test_delete_rule(client, staff, rule):
    client.force_login(staff)
    r = client.delete(f"/api/correlations/rules/{rule.pk}/")
    assert r.status_code == 204
    assert not CorrelationRule.objects.filter(pk=rule.pk).exists()


@pytest.mark.django_db
def test_delete_rule_requires_staff(client, non_staff, rule):
    client.force_login(non_staff)
    r = client.delete(f"/api/correlations/rules/{rule.pk}/")
    assert r.status_code == 403


# ── GET /api/correlations/catalog/ ───────────────────────────────────────────

@pytest.mark.django_db
def test_catalog_requires_auth(client):
    r = client.get("/api/correlations/catalog/")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_catalog_returns_fields(client, staff):
    client.force_login(staff)
    r = client.get("/api/correlations/catalog/")
    assert r.status_code == 200
    data = r.json()
    assert "alert_field" in data["fields"]
    assert "entity" in data["fields"]
    assert "source_ref" in data["fields"]
    assert "alert_field" in data["operators"]
    assert "severity" in [f["value"] for f in data["fields"]["alert_field"]]
    assert "source.ip" in [f["value"] for f in data["fields"]["entity"]]


# ── GET /api/correlations/rules/<pk>/ ────────────────────────────────────────

@pytest.mark.django_db
def test_get_rule_detail(client, staff, rule):
    client.force_login(staff)
    r = client.get(f"/api/correlations/rules/{rule.pk}/")
    assert r.status_code == 200
    assert r.json()["name"] == "Port Scan Rule"


# ── GET /api/correlations/org-system-rules/ ──────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def system_rule(db):
    return CorrelationRule.objects.create(
        name="Port Scan",
        organization=None,
        correlation_key="source.ip",
        window_minutes=30,
        severity="high",
        enabled=True,
    )


@pytest.mark.django_db
def test_list_org_system_rules_requires_staff(client, non_staff, org):
    client.force_login(non_staff)
    r = client.get(f"/api/correlations/org-system-rules/?org={org.slug}")
    assert r.status_code == 403


@pytest.mark.django_db
def test_list_org_system_rules_requires_org_param(client, staff):
    client.force_login(staff)
    r = client.get("/api/correlations/org-system-rules/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_list_org_system_rules_returns_system_rules_only(client, staff, org, system_rule):
    org_rule = CorrelationRule.objects.create(
        name="Org-owned Rule",
        organization=org,
        correlation_key="none",
        window_minutes=60,
        severity="medium",
        enabled=True,
    )
    client.force_login(staff)
    r = client.get(f"/api/correlations/org-system-rules/?org={org.slug}")
    assert r.status_code == 200
    data = r.json()
    names = [d["name"] for d in data]
    assert "Port Scan" in names
    assert "Org-owned Rule" not in names


@pytest.mark.django_db
def test_list_org_system_rules_muted_flag_false_when_not_muted(client, staff, org, system_rule):
    client.force_login(staff)
    r = client.get(f"/api/correlations/org-system-rules/?org={org.slug}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["muted"] is False


@pytest.mark.django_db
def test_list_org_system_rules_muted_flag_true_when_muted(client, staff, org, system_rule):
    from correlations.models import SystemRuleMute
    SystemRuleMute.objects.create(organization=org, rule=system_rule)
    client.force_login(staff)
    r = client.get(f"/api/correlations/org-system-rules/?org={org.slug}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["muted"] is True


# ── POST /api/correlations/org-system-rules/<pk>/mute/ ───────────────────────

@pytest.mark.django_db
def test_mute_system_rule_requires_staff(client, non_staff, org, system_rule):
    client.force_login(non_staff)
    r = client.post(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/",
        data={"org": org.slug},
        content_type="application/json",
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_mute_system_rule_creates_mute_record(client, staff, org, system_rule):
    from correlations.models import SystemRuleMute
    client.force_login(staff)
    r = client.post(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/",
        data={"org": org.slug},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["muted"] is True
    assert SystemRuleMute.objects.filter(organization=org, rule=system_rule).exists()


@pytest.mark.django_db
def test_mute_system_rule_idempotent(client, staff, org, system_rule):
    from correlations.models import SystemRuleMute
    client.force_login(staff)
    client.post(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/",
        data={"org": org.slug},
        content_type="application/json",
    )
    r = client.post(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/",
        data={"org": org.slug},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert SystemRuleMute.objects.filter(organization=org, rule=system_rule).count() == 1


@pytest.mark.django_db
def test_mute_org_owned_rule_returns_404(client, staff, org):
    org_rule = CorrelationRule.objects.create(
        name="Org Rule",
        organization=org,
        correlation_key="none",
        window_minutes=60,
        severity="medium",
        enabled=True,
    )
    client.force_login(staff)
    r = client.post(
        f"/api/correlations/org-system-rules/{org_rule.pk}/mute/",
        data={"org": org.slug},
        content_type="application/json",
    )
    assert r.status_code == 404


# ── DELETE /api/correlations/org-system-rules/<pk>/mute/ ─────────────────────

@pytest.mark.django_db
def test_unmute_system_rule_removes_mute_record(client, staff, org, system_rule):
    from correlations.models import SystemRuleMute
    SystemRuleMute.objects.create(organization=org, rule=system_rule)
    client.force_login(staff)
    r = client.delete(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/?org={org.slug}"
    )
    assert r.status_code == 200
    assert r.json()["muted"] is False
    assert not SystemRuleMute.objects.filter(organization=org, rule=system_rule).exists()


@pytest.mark.django_db
def test_unmute_system_rule_no_op_when_not_muted(client, staff, org, system_rule):
    client.force_login(staff)
    r = client.delete(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/?org={org.slug}"
    )
    assert r.status_code == 200
    assert r.json()["muted"] is False


@pytest.mark.django_db
def test_unmute_system_rule_requires_staff(client, non_staff, org, system_rule):
    client.force_login(non_staff)
    r = client.delete(
        f"/api/correlations/org-system-rules/{system_rule.pk}/mute/?org={org.slug}"
    )
    assert r.status_code == 403
