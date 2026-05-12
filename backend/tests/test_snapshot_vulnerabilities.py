from unittest.mock import MagicMock, patch

import pytest

from notifications.models import Notification
from security.models import Organization, VulnerabilitySnapshot
from security.wazuh import WazuhAPIError


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def beta(db):
    return Organization.objects.create(name="Beta", slug="beta", wazuh_group="beta")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture
def inactive_staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="inactive_staff", password="p", is_staff=True, is_active=False
    )


RAW_AGENTS = [
    {"id": "001", "status": "active"},
    {"id": "002", "status": "disconnected"},
]

VULNS = [
    {"cve": "CVE-2024-0001", "severity": "critical"},
    {"cve": "CVE-2024-0002", "severity": "high"},
    {"cve": "CVE-2024-0003", "severity": "high"},
    {"cve": "CVE-2024-0004", "severity": "medium"},
]


def _run():
    from security.tasks import snapshot_vulnerabilities
    snapshot_vulnerabilities()


# ── happy path ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_snapshot_created_for_org(MockWazuh, MockOS, acme):
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    MockOS.return_value.get_fleet_vulnerabilities.return_value = {"vulnerabilities": VULNS}
    _run()
    snap = VulnerabilitySnapshot.objects.get(organization=acme)
    assert snap.critical == 1
    assert snap.high == 2
    assert snap.medium == 1
    assert snap.low == 0
    assert set(snap.cve_ids) == {"CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003", "CVE-2024-0004"}


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_only_active_agents_queried(MockWazuh, MockOS, acme):
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    MockOS.return_value.get_fleet_vulnerabilities.return_value = {"vulnerabilities": []}
    _run()
    call_args = MockOS.return_value.get_fleet_vulnerabilities.call_args
    assert call_args[0][0] == ["001"]


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_no_active_agents_produces_empty_snapshot(MockWazuh, MockOS, acme):
    MockWazuh.return_value.get_agents.return_value = [{"id": "001", "status": "disconnected"}]
    _run()
    MockOS.return_value.get_fleet_vulnerabilities.assert_not_called()
    snap = VulnerabilitySnapshot.objects.get(organization=acme)
    assert snap.critical == 0
    assert snap.cve_ids == []


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_new_and_resolved_counts(MockWazuh, MockOS, acme, django_db_setup):
    from datetime import date, timedelta
    prev_date = date.today() - timedelta(days=1)
    VulnerabilitySnapshot.objects.create(
        organization=acme,
        date=prev_date,
        cve_ids=["CVE-2024-0001", "CVE-OLD-0001"],
    )
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    MockOS.return_value.get_fleet_vulnerabilities.return_value = {"vulnerabilities": VULNS}
    _run()
    snap = VulnerabilitySnapshot.objects.get(organization=acme, date=date.today())
    # CVE-2024-0002/0003/0004 are new; CVE-OLD-0001 is resolved
    assert snap.new_count == 3
    assert snap.resolved_count == 1


# ── error path ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_wazuh_error_notifies_staff(MockWazuh, MockOS, acme, staff):
    MockWazuh.return_value.get_agents.side_effect = WazuhAPIError("connection refused")
    _run()
    notif = Notification.objects.filter(recipient=staff, kind="system_alert").first()
    assert notif is not None
    assert "Acme" in notif.payload["body"]


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_error_does_not_notify_inactive_staff(MockWazuh, MockOS, acme, inactive_staff):
    MockWazuh.return_value.get_agents.side_effect = WazuhAPIError("err")
    _run()
    assert not Notification.objects.filter(recipient=inactive_staff, kind="system_alert").exists()


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_error_on_one_org_does_not_block_others(MockWazuh, MockOS, acme, beta):
    def get_agents_side_effect(group):
        if group == "acme":
            raise WazuhAPIError("acme down")
        return []

    MockWazuh.return_value.get_agents.side_effect = get_agents_side_effect
    _run()
    # Beta should still get a snapshot
    assert VulnerabilitySnapshot.objects.filter(organization=beta).exists()


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_error_no_snapshot_created(MockWazuh, MockOS, acme):
    MockWazuh.return_value.get_agents.side_effect = WazuhAPIError("err")
    _run()
    assert not VulnerabilitySnapshot.objects.filter(organization=acme).exists()


@pytest.mark.django_db
@patch("security.opensearch.OpenSearchClient")
@patch("security.wazuh.WazuhClient")
def test_error_logged(MockWazuh, MockOS, acme, caplog):
    import logging
    MockWazuh.return_value.get_agents.side_effect = WazuhAPIError("boom")
    with caplog.at_level(logging.ERROR, logger="security.tasks"):
        _run()
    assert "acme" in caplog.text
