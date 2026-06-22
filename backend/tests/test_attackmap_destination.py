"""Destination resolver — pure resolution + cached reverse-map build (PRD #594 #597)."""
import pytest
from unittest.mock import MagicMock

from attackmap.destination import DestinationResolver, build_reverse_map
from security.models import Organization

HOME = (52.37, 4.9, "Shared Infrastructure")


def test_known_agent_resolves_to_its_org_coordinates():
    resolver = DestinationResolver({"001": (51.5, -0.12, "Acme")}, HOME)
    assert resolver.resolve("001") == (51.5, -0.12, "Acme")


def test_infra_agent_000_resolves_to_home():
    resolver = DestinationResolver({"001": (51.5, -0.12, "Acme")}, HOME)
    assert resolver.resolve("000") == HOME


def test_unknown_agent_falls_back_to_home():
    resolver = DestinationResolver({}, HOME)
    assert resolver.resolve("999") == HOME


def test_org_without_location_lands_on_home_point_under_its_label():
    resolver = DestinationResolver({"007": (None, None, "Globex")}, HOME)
    lat, lng, label = resolver.resolve("007")
    assert (lat, lng) == (HOME[0], HOME[1])
    assert label == "Globex"


@pytest.mark.django_db
def test_build_reverse_map_from_org_group_membership():
    Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme", latitude=51.5, longitude=-0.12)
    wazuh = MagicMock()
    wazuh.get_agents.return_value = [{"id": "001"}, {"id": "002"}]
    reverse = build_reverse_map(wazuh)
    assert reverse["001"] == (51.5, -0.12, "Acme")
    assert reverse["002"] == (51.5, -0.12, "Acme")


@pytest.mark.django_db
def test_build_reverse_map_survives_wazuh_failure_for_one_org():
    Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")
    wazuh = MagicMock()
    wazuh.get_agents.side_effect = RuntimeError("Wazuh down")
    # Must not raise — a flaky API just yields an empty map for that org.
    assert build_reverse_map(wazuh) == {}
