"""Hunt scope resolution for Shared Infrastructure (issues #494, #496; ADR-0017).

An all-orgs hunt includes the Infrastructure org, special-cased to a positive
agent.id="000" filter resolved *without* get_agents. A narrowed hunt sees "000" only
when the staff member explicitly selected Infrastructure.
"""
from unittest.mock import MagicMock

import pytest

from hunts.models import Hunt
from hunts.scope import INFRASTRUCTURE_AGENT_ID, resolve_scope
from security.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def fake_wazuh():
    wc = MagicMock()
    wc.get_agents.return_value = [{"id": "001"}, {"id": "002"}]
    return wc


def test_all_orgs_hunt_includes_infrastructure_scope(acme, fake_wazuh):
    infra = Organization.get_infrastructure()
    hunt = Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=True)

    scopes = resolve_scope(hunt, wazuh_client=fake_wazuh)

    infra_scopes = [s for s in scopes if s.is_infrastructure]
    assert len(infra_scopes) == 1
    assert infra_scopes[0].org_id == infra.id
    assert infra_scopes[0].agent_ids == [INFRASTRUCTURE_AGENT_ID]


def test_infrastructure_scope_does_not_call_get_agents(acme, fake_wazuh):
    Organization.get_infrastructure()
    hunt = Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=True)

    resolve_scope(hunt, wazuh_client=fake_wazuh)

    # get_agents is called for the real tenant, never with the infra group ("").
    called_groups = [c.args[0] for c in fake_wazuh.get_agents.call_args_list]
    assert "acme" in called_groups
    assert "" not in called_groups


def test_narrowed_hunt_without_infrastructure_has_no_000(acme, fake_wazuh):
    Organization.get_infrastructure()
    hunt = Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=False)
    hunt.scope_orgs.set([acme])

    scopes = resolve_scope(hunt, wazuh_client=fake_wazuh)

    assert all(not s.is_infrastructure for s in scopes)
    assert all(INFRASTRUCTURE_AGENT_ID not in s.agent_ids for s in scopes)


def test_resolve_scope_retains_agent_assets(acme):
    # #512: the name/ip/os fetched for agent_ids is kept for the LLM asset inventory.
    wc = MagicMock()
    wc.get_agents.return_value = [
        {"id": "001", "name": "web01", "ip": "10.0.0.5", "os": {"name": "Ubuntu 22.04"}},
        {"id": "002", "name": "db01", "ip": "10.0.0.6", "os": {"name": "Debian 12"}},
    ]
    hunt = Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=False)
    hunt.scope_orgs.set([acme])

    scopes = resolve_scope(hunt, wazuh_client=wc)

    acme_scope = next(s for s in scopes if s.org_id == acme.id)
    assert acme_scope.agent_ids == ["001", "002"]
    assert acme_scope.agents == [
        {"id": "001", "name": "web01", "ip": "10.0.0.5", "os": "Ubuntu 22.04"},
        {"id": "002", "name": "db01", "ip": "10.0.0.6", "os": "Debian 12"},
    ]


def test_narrowed_hunt_infrastructure_only_resolves_to_000(fake_wazuh):
    infra = Organization.get_infrastructure()
    hunt = Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=False)
    hunt.scope_orgs.set([infra])

    scopes = resolve_scope(hunt, wazuh_client=fake_wazuh)

    assert len(scopes) == 1
    assert scopes[0].is_infrastructure
    assert scopes[0].agent_ids == [INFRASTRUCTURE_AGENT_ID]
    fake_wazuh.get_agents.assert_not_called()
