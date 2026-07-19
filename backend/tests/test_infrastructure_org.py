"""Infrastructure pseudo-org foundation (issue #493, ADR-0017).

The Infrastructure org exists, is reachable via a helper, and stays out of every
"real tenant" code path: the tenants() accessor excludes it, the System Search Rule
fan-out skips it, and the staff org-list endpoint hides it by default.
"""
from unittest.mock import patch

import pytest

from security.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def test_infrastructure_org_seeded_by_migration():
    infra = Organization.objects.filter(is_infrastructure=True)
    assert infra.count() == 1


def test_get_infrastructure_is_idempotent():
    a = Organization.get_infrastructure()
    b = Organization.get_infrastructure()
    assert a.pk == b.pk
    assert Organization.objects.filter(is_infrastructure=True).count() == 1


def test_tenants_accessor_excludes_infrastructure(acme):
    infra = Organization.get_infrastructure()
    tenants = list(Organization.objects.tenants())
    assert acme in tenants
    assert infra not in tenants


def test_all_still_includes_infrastructure(acme):
    infra = Organization.get_infrastructure()
    assert infra in set(Organization.objects.all())


def test_system_search_rule_fanout_skips_infrastructure(acme):
    """run_scheduled_search_rule must not evaluate a system rule against the infra org."""
    from correlations.models import SearchRule
    from correlations.tasks import run_scheduled_search_rule

    Organization.get_infrastructure()
    rule = SearchRule.objects.create(
        organization=None, name="sys", severity="high",
        window_minutes=60, interval_minutes=15, max_findings_per_run=50,
    )

    seen = []
    with patch(
        "correlations.services.search_evaluator.run",
        side_effect=lambda r, org: seen.append(org),
    ):
        run_scheduled_search_rule(rule.id)

    seen_infra = [o for o in seen if o.is_infrastructure]
    assert seen_infra == []
    assert acme in seen


def test_org_list_endpoint_hides_infrastructure_by_default(admin_client, acme):
    Organization.get_infrastructure()
    resp = admin_client.get("/api/security/organizations/")
    assert resp.status_code == 200
    slugs = [o["slug"] for o in resp.json()]
    assert "acme" in slugs
    assert "infrastructure" not in slugs


def test_org_list_endpoint_includes_infrastructure_with_flag(admin_client, acme):
    Organization.get_infrastructure()
    resp = admin_client.get("/api/security/organizations/?include_infrastructure=1")
    assert resp.status_code == 200
    slugs = [o["slug"] for o in resp.json()]
    assert "acme" in slugs
    assert "infrastructure" in slugs


def test_infrastructure_org_triage_thresholds_are_patchable(admin_client):
    """#720: the Infrastructure org's AI-triage settings can be edited from the
    management page (which resolves the org by slug)."""
    infra = Organization.get_infrastructure()
    resp = admin_client.patch(
        f"/api/security/organizations/{infra.slug}/",
        data={"triage_fp_threshold": 0.7, "triage_work_threshold": 0.6},
        content_type="application/json",
    )
    assert resp.status_code == 200
    infra.refresh_from_db()
    assert infra.triage_fp_threshold == 0.7
    assert infra.triage_work_threshold == 0.6
