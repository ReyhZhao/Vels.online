from unittest.mock import patch

import pytest

from incidents.models import Asset
from security.models import Organization
from security.wazuh import WazuhAPIError


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def beta(db):
    return Organization.objects.create(name="Beta", slug="beta", wazuh_group="beta")


RAW_AGENTS = [
    {"id": "001", "name": "host-1", "ip": "10.0.0.1", "status": "active"},
    {"id": "002", "name": "host-2", "ip": "10.0.0.2", "status": "active"},
]


def _run():
    from incidents.tasks import sync_wazuh_agents
    sync_wazuh_agents()


# ── asset creation ────────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_creates_assets_for_new_agents(MockWazuh, acme):
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    _run()
    assert Asset.objects.filter(organization=acme, kind=Asset.KIND_HOST).count() == 2
    asset = Asset.objects.get(organization=acme, agent_name="host-1")
    assert asset.name == "host-1"
    assert str(asset.ip_address) == "10.0.0.1"
    assert asset.is_active is True
    assert asset.last_seen_at is not None


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_updates_last_seen_at_on_resync(MockWazuh, acme):
    from django.utils import timezone
    from datetime import timedelta

    old_time = timezone.now() - timedelta(days=5)
    Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, agent_name="host-1",
        name="host-1", is_active=True, last_seen_at=old_time,
    )
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    _run()
    asset = Asset.objects.get(organization=acme, agent_name="host-1")
    assert asset.last_seen_at > old_time


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_marks_absent_agents_inactive(MockWazuh, acme):
    Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, agent_name="old-host",
        name="old-host", is_active=True,
    )
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    _run()
    old = Asset.objects.get(organization=acme, agent_name="old-host")
    assert old.is_active is False


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_does_not_delete_absent_agents(MockWazuh, acme):
    Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, agent_name="old-host",
        name="old-host", is_active=True,
    )
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    _run()
    assert Asset.objects.filter(organization=acme, agent_name="old-host").exists()


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_idempotent_double_sync(MockWazuh, acme):
    MockWazuh.return_value.get_agents.return_value = RAW_AGENTS
    _run()
    _run()
    assert Asset.objects.filter(organization=acme, kind=Asset.KIND_HOST).count() == 2


# ── stale cleanup ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_deletes_stale_assets(MockWazuh, acme, monkeypatch):
    from django.utils import timezone
    from datetime import timedelta

    monkeypatch.setenv("ASSET_STALE_DAYS", "30")
    stale_time = timezone.now() - timedelta(days=31)
    Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, agent_name="stale-host",
        name="stale-host", is_active=False, last_seen_at=stale_time,
    )
    MockWazuh.return_value.get_agents.return_value = []
    _run()
    assert not Asset.objects.filter(organization=acme, agent_name="stale-host").exists()


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_does_not_delete_recent_assets(MockWazuh, acme, monkeypatch):
    from django.utils import timezone
    from datetime import timedelta

    monkeypatch.setenv("ASSET_STALE_DAYS", "30")
    recent_time = timezone.now() - timedelta(days=10)
    Asset.objects.create(
        organization=acme, kind=Asset.KIND_HOST, agent_name="recent-host",
        name="recent-host", is_active=False, last_seen_at=recent_time,
    )
    MockWazuh.return_value.get_agents.return_value = []
    _run()
    assert Asset.objects.filter(organization=acme, agent_name="recent-host").exists()


# ── error handling ────────────────────────────────────────────────────────────


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_wazuh_error_does_not_abort_other_orgs(MockWazuh, acme, beta):
    def get_agents_side_effect(group):
        if group == "acme":
            raise WazuhAPIError("acme down")
        return RAW_AGENTS

    MockWazuh.return_value.get_agents.side_effect = get_agents_side_effect
    _run()
    assert Asset.objects.filter(organization=beta, kind=Asset.KIND_HOST).count() == 2
    assert not Asset.objects.filter(organization=acme, kind=Asset.KIND_HOST).exists()


@pytest.mark.django_db
@patch("security.wazuh.WazuhClient")
def test_wazuh_error_is_logged(MockWazuh, acme, caplog):
    import logging
    MockWazuh.return_value.get_agents.side_effect = WazuhAPIError("boom")
    with caplog.at_level(logging.ERROR, logger="incidents.tasks"):
        _run()
    assert "acme" in caplog.text
