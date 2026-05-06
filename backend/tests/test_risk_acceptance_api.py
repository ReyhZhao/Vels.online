from unittest.mock import patch

import pytest
from security.models import Organization, OrganizationMembership, RiskAcceptance, WorkPackage, WorkPackageItem


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


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
def active_package(acme):
    return WorkPackage.objects.create(org=acme)


@pytest.fixture
def item(active_package):
    return WorkPackageItem.objects.create(
        work_package=active_package,
        cve_id="CVE-2024-0001",
        severity="critical",
        cvss_score=9.8,
        description="A critical flaw.",
        affected_agent_count=3,
        impact_score=30.0,
    )


def _make_item(pkg, cve_id, status="open", note=""):
    return WorkPackageItem.objects.create(
        work_package=pkg,
        cve_id=cve_id,
        severity="high",
        cvss_score=7.0,
        description="",
        affected_agent_count=1,
        impact_score=7.0,
        status=status,
        note=note,
    )


def patch_item(client, item_id, data):
    return client.patch(
        f"/api/security/work-package/items/{item_id}/",
        data,
        content_type="application/json",
    )


# ================================================================ PATCH → accepted_risk creates RiskAcceptance


@pytest.mark.django_db
def test_patch_to_accepted_risk_creates_risk_acceptance(client, acme_member, item):
    client.force_login(acme_member)
    response = patch_item(client, item.id, {"status": "accepted_risk", "note": "Mitigated externally."})
    assert response.status_code == 200
    assert RiskAcceptance.objects.filter(org=item.work_package.org, cve_id="CVE-2024-0001").exists()


@pytest.mark.django_db
def test_patch_to_accepted_risk_captures_user_and_fields(client, acme_member, item):
    client.force_login(acme_member)
    patch_item(client, item.id, {"status": "accepted_risk", "note": "Known issue."})
    ra = RiskAcceptance.objects.get(org=item.work_package.org, cve_id="CVE-2024-0001")
    assert ra.accepted_by == acme_member
    assert ra.note == "Known issue."
    assert ra.severity == "critical"
    assert ra.cvss_score == 9.8


@pytest.mark.django_db
def test_patch_to_accepted_risk_twice_updates_existing(client, acme_member, item, acme):
    client.force_login(acme_member)
    patch_item(client, item.id, {"status": "accepted_risk", "note": "First note."})
    patch_item(client, item.id, {"status": "accepted_risk", "note": "Updated note."})
    assert RiskAcceptance.objects.filter(org=acme, cve_id="CVE-2024-0001").count() == 1
    ra = RiskAcceptance.objects.get(org=acme, cve_id="CVE-2024-0001")
    assert ra.note == "Updated note."


# ================================================================ PATCH away from accepted_risk reverts items


@pytest.mark.django_db
def test_patch_away_from_accepted_risk_deletes_risk_acceptance(client, acme_member, item, acme):
    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member,
        severity="critical", cvss_score=9.8,
    )
    item.status = "accepted_risk"
    item.note = "Some note."
    item.save()

    client.force_login(acme_member)
    patch_item(client, item.id, {"status": "open"})

    assert not RiskAcceptance.objects.filter(org=acme, cve_id="CVE-2024-0001").exists()


@pytest.mark.django_db
def test_patch_away_from_accepted_risk_reverts_all_items_to_open(client, acme_member, active_package, acme):
    alice = acme_member
    item1 = _make_item(active_package, "CVE-2024-0001", status="accepted_risk", note="note1")
    pkg2 = WorkPackage.objects.create(org=acme, status=WorkPackage.STATUS_ARCHIVED)
    item2 = _make_item(pkg2, "CVE-2024-0001", status="accepted_risk", note="note2")

    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=alice,
        severity="high", cvss_score=7.0,
    )

    client.force_login(alice)
    response = patch_item(client, item1.id, {"status": "open"})

    assert response.status_code == 200
    item1.refresh_from_db()
    item2.refresh_from_db()
    assert item1.status == "open"
    assert item1.note == ""
    assert item2.status == "open"
    assert item2.note == ""


@pytest.mark.django_db
def test_patch_away_does_not_affect_other_cves(client, acme_member, active_package, acme):
    item_cve1 = _make_item(active_package, "CVE-2024-0001", status="accepted_risk")
    item_cve2 = _make_item(active_package, "CVE-2024-0002", status="accepted_risk", note="keep me")

    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0,
    )
    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0002", accepted_by=acme_member, severity="high", cvss_score=7.0,
    )

    client.force_login(acme_member)
    patch_item(client, item_cve1.id, {"status": "open"})

    item_cve2.refresh_from_db()
    assert item_cve2.status == "accepted_risk"
    assert item_cve2.note == "keep me"
    assert RiskAcceptance.objects.filter(org=acme, cve_id="CVE-2024-0002").exists()


# ================================================================ GET /api/security/risk-acceptances/


@pytest.mark.django_db
def test_list_risk_acceptances_requires_authentication(client, acme):
    response = client.get("/api/security/risk-acceptances/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_risk_acceptances_non_member_gets_403(client, alice, acme):
    client.force_login(alice)
    response = client.get("/api/security/risk-acceptances/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_risk_acceptances_missing_org_returns_400(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/risk-acceptances/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_list_risk_acceptances_returns_org_records(client, acme_member, acme):
    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member,
        severity="critical", cvss_score=9.8, note="test note",
    )
    client.force_login(acme_member)
    response = client.get("/api/security/risk-acceptances/?org=acme")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cve_id"] == "CVE-2024-0001"
    assert data[0]["org_slug"] == "acme"
    assert data[0]["note"] == "test note"
    assert data[0]["severity"] == "critical"


@pytest.mark.django_db
def test_list_risk_acceptances_excludes_other_orgs(client, acme_member, acme, contoso, django_user_model):
    bob = django_user_model.objects.create_user(username="bob", password="pass")
    RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)
    RiskAcceptance.objects.create(org=contoso, cve_id="CVE-2024-0002", accepted_by=bob, severity="low", cvss_score=3.0)

    client.force_login(acme_member)
    response = client.get("/api/security/risk-acceptances/?org=acme")
    assert response.status_code == 200
    cve_ids = [r["cve_id"] for r in response.json()]
    assert "CVE-2024-0001" in cve_ids
    assert "CVE-2024-0002" not in cve_ids


@pytest.mark.django_db
def test_list_risk_acceptances_staff_can_access_any_org(admin_client, acme, alice):
    RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=alice, severity="high", cvss_score=7.0)
    response = admin_client.get("/api/security/risk-acceptances/?org=acme")
    assert response.status_code == 200
    assert len(response.json()) == 1


# ================================================================ DELETE /api/security/risk-acceptances/<id>/


@pytest.mark.django_db
def test_delete_risk_acceptance_requires_authentication(client, acme, acme_member):
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)
    response = client.delete(f"/api/security/risk-acceptances/{ra.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_risk_acceptance_non_member_gets_403(client, acme, acme_member, django_user_model):
    outsider = django_user_model.objects.create_user(username="outsider", password="pass")
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)
    client.force_login(outsider)
    response = client.delete(f"/api/security/risk-acceptances/{ra.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_risk_acceptance_not_found_returns_404(client, acme_member):
    client.force_login(acme_member)
    response = client.delete("/api/security/risk-acceptances/99999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_risk_acceptance_removes_record(client, acme_member, acme):
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)
    client.force_login(acme_member)
    response = client.delete(f"/api/security/risk-acceptances/{ra.id}/")
    assert response.status_code == 204
    assert not RiskAcceptance.objects.filter(pk=ra.id).exists()


@pytest.mark.django_db
def test_delete_risk_acceptance_reverts_items(client, acme_member, active_package, acme):
    item = _make_item(active_package, "CVE-2024-0001", status="accepted_risk", note="accepted")
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)

    client.force_login(acme_member)
    client.delete(f"/api/security/risk-acceptances/{ra.id}/")

    item.refresh_from_db()
    assert item.status == "open"
    assert item.note == ""


@pytest.mark.django_db
def test_delete_risk_acceptance_org_member_can_delete(client, acme_member, acme, django_user_model):
    bob = django_user_model.objects.create_user(username="bob", password="pass")
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=bob, severity="high", cvss_score=7.0)
    client.force_login(acme_member)
    response = client.delete(f"/api/security/risk-acceptances/{ra.id}/")
    assert response.status_code == 204


@pytest.mark.django_db
def test_delete_risk_acceptance_staff_can_delete(admin_client, acme, acme_member):
    ra = RiskAcceptance.objects.create(org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="high", cvss_score=7.0)
    response = admin_client.delete(f"/api/security/risk-acceptances/{ra.id}/")
    assert response.status_code == 204


# ================================================================ generate/add_more skip accepted CVEs


_WAZUH_AGENTS = [{"id": "001", "status": "active"}]
_VULNS = {
    "vulnerabilities": [
        {"cve": "CVE-2024-0001", "severity": "critical", "affected_agents": 3, "cvss_score": 9.8},
        {"cve": "CVE-2024-0002", "severity": "high", "affected_agents": 2, "cvss_score": 7.5},
    ],
    "total": 2,
    "stats": {"critical": 1, "high": 1, "medium": 0, "low": 0, "affected_systems": 2, "fixable": 1},
}


@pytest.mark.django_db
@patch("security.work_package_service.WazuhClient")
@patch("security.work_package_service.OpenSearchClient")
def test_generate_skips_accepted_cves(mock_os_cls, mock_wazuh_cls, acme, acme_member):
    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="critical", cvss_score=9.8,
    )

    mock_wazuh = mock_wazuh_cls.return_value
    mock_wazuh.get_agents.return_value = _WAZUH_AGENTS
    mock_os = mock_os_cls.return_value
    mock_os.get_fleet_vulnerabilities.return_value = _VULNS
    mock_os.get_cve_affected_agents.return_value = []

    from security.work_package_service import generate_work_package
    pkg = generate_work_package(acme)

    assert pkg is not None
    cve_ids = list(pkg.items.values_list("cve_id", flat=True))
    assert "CVE-2024-0001" not in cve_ids
    assert "CVE-2024-0002" in cve_ids


@pytest.mark.django_db
@patch("security.work_package_service.WazuhClient")
@patch("security.work_package_service.OpenSearchClient")
def test_add_more_skips_accepted_cves(mock_os_cls, mock_wazuh_cls, acme, acme_member):
    pkg = WorkPackage.objects.create(org=acme)
    _make_item(pkg, "CVE-2024-0003")

    RiskAcceptance.objects.create(
        org=acme, cve_id="CVE-2024-0001", accepted_by=acme_member, severity="critical", cvss_score=9.8,
    )

    mock_wazuh = mock_wazuh_cls.return_value
    mock_wazuh.get_agents.return_value = _WAZUH_AGENTS
    mock_os = mock_os_cls.return_value
    mock_os.get_fleet_vulnerabilities.return_value = _VULNS
    mock_os.get_cve_affected_agents.return_value = []

    from security.work_package_service import add_more_items
    new_items, _ = add_more_items(pkg)

    cve_ids = [i.cve_id for i in new_items]
    assert "CVE-2024-0001" not in cve_ids
