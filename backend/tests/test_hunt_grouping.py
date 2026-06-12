"""Finding grouping → propose-and-confirm Incident per org (module 5, issue #478).

Asserts: findings group by affected org; confirming one org materialises its matched docs
as Alerts (source_kind=threat_hunt) linked to a fresh Incident in *that org's* scope; the
operation is idempotent; and a cross-org hunt yields one incident per org, never joined.
"""
import pytest

from alerts.models import Alert
from hunts.grouping import (
    group_findings_by_org,
    materialise_findings_for_org,
    proposed_incidents,
)
from hunts.models import Hunt, HuntFinding
from incidents.models import Incident
from security.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def orgs(db):
    a = Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")
    b = Organization.objects.create(name="Beta", slug="beta", wazuh_group="beta")
    return a, b


@pytest.fixture
def hunt(db):
    return Hunt.objects.create(title="t", seed_kind="question", seed_text="q")


def _finding(hunt, org, doc_id):
    return HuntFinding.objects.create(
        hunt=hunt, organization=org, lens="ioc_search",
        source_index="wazuh-alerts", wazuh_doc_id=doc_id,
        raw_doc={"agent": {"name": f"host-{doc_id}"}, "rule": {"description": "malware"}},
        summary="malware",
    )


def test_findings_group_by_org(hunt, orgs):
    a, b = orgs
    _finding(hunt, a, "1")
    _finding(hunt, a, "2")
    _finding(hunt, b, "3")

    groups = group_findings_by_org(hunt)

    assert set(groups.keys()) == {a, b}
    assert len(groups[a]) == 2
    assert len(groups[b]) == 1


def test_proposed_incidents_lists_one_entry_per_org(hunt, orgs):
    a, b = orgs
    _finding(hunt, a, "1")
    _finding(hunt, b, "2")

    proposals = proposed_incidents(hunt)

    ids = {p["organization_id"]: p["finding_count"] for p in proposals}
    assert ids == {a.id: 1, b.id: 1}


def test_confirm_materialises_alerts_into_a_new_incident_in_that_org(hunt, orgs):
    a, _b = orgs
    _finding(hunt, a, "1")
    _finding(hunt, a, "2")

    incident = materialise_findings_for_org(hunt, a)

    assert incident is not None
    assert incident.organization == a
    assert incident.source_kind == Incident.SOURCE_THREAT_HUNT
    alerts = Alert.objects.filter(incident=incident)
    assert alerts.count() == 2
    assert all(al.source_kind == "threat_hunt" for al in alerts)
    assert all(al.organization == a for al in alerts)
    # findings now point at the incident
    assert hunt.findings.filter(organization=a, materialised_incident=incident).count() == 2


def test_confirm_is_idempotent(hunt, orgs):
    a, _b = orgs
    _finding(hunt, a, "1")

    first = materialise_findings_for_org(hunt, a)
    second = materialise_findings_for_org(hunt, a)

    assert first is not None
    assert second is None  # nothing left to materialise
    assert Incident.objects.filter(organization=a, source_kind=Incident.SOURCE_THREAT_HUNT).count() == 1


def test_confirm_infrastructure_findings_into_incident_in_infra_org(hunt):
    """Agent-less Shared Infrastructure findings confirm into an Incident in the infra
    org, and a doc with no agent.name materialises without erroring (issue #495)."""
    infra = Organization.get_infrastructure()
    # An agent-less firewall doc: agent.id="000" present, but no agent.name.
    HuntFinding.objects.create(
        hunt=hunt, organization=infra, lens="ioc_search",
        source_index="wazuh-alerts", wazuh_doc_id="fw-1",
        raw_doc={"agent": {"id": "000"}, "rule": {"description": "fw drop"}},
        summary="perimeter drop",
    )

    # the infra group is offered as its own proposed incident
    assert any(p["organization_id"] == infra.id for p in proposed_incidents(hunt))

    incident = materialise_findings_for_org(hunt, infra)

    assert incident is not None
    assert incident.organization == infra
    alerts = Alert.objects.filter(incident=incident)
    assert alerts.count() == 1
    assert alerts.first().organization == infra
    # re-confirming does not duplicate
    assert materialise_findings_for_org(hunt, infra) is None


def test_promotion_populates_iocs_and_rich_description(hunt, orgs):
    """Observables in the matched docs become IOCs and the description carries an
    evidence digest (issue #497)."""
    from incidents.models import IOC

    a, _b = orgs
    HuntFinding.objects.create(
        hunt=hunt, organization=a, lens="ioc_search",
        source_index="wazuh-alerts", wazuh_doc_id="d1",
        raw_doc={
            "agent": {"name": "web-01"},
            "rule": {"description": "Connection to known-bad host"},
            "data": {"srcip": "8.8.8.8", "url": "malicious-c2.com"},
        },
        summary="beaconing to malicious-c2.com",
    )

    incident = materialise_findings_for_org(hunt, a)

    ioc_values = set(IOC.objects.filter(incident=incident).values_list("value", flat=True))
    assert "8.8.8.8" in ioc_values
    assert any("malicious-c2.com" in v for v in ioc_values)
    # description digest carries the host, rule and summary
    assert "web-01" in incident.description
    assert "Connection to known-bad host" in incident.description
    assert "beaconing to malicious-c2.com" in incident.description


def test_promotion_iocs_are_idempotent(hunt, orgs):
    """Re-running extraction over the same incident does not duplicate IOCs (#497)."""
    from incidents.models import IOC

    a, _b = orgs
    HuntFinding.objects.create(
        hunt=hunt, organization=a, lens="ioc_search",
        source_index="wazuh-alerts", wazuh_doc_id="d1",
        raw_doc={"agent": {"name": "web-01"}, "data": {"srcip": "9.9.9.9"}},
        summary="hit",
    )

    incident = materialise_findings_for_org(hunt, a)
    before = IOC.objects.filter(incident=incident).count()
    # second confirm has nothing left to materialise, but extraction must stay idempotent
    from incidents.services.ioc_extraction import extract_and_save_iocs
    extract_and_save_iocs(incident)

    assert before >= 1
    assert IOC.objects.filter(incident=incident).count() == before


def test_cross_org_hunt_yields_one_incident_per_org_never_joined(hunt, orgs):
    a, b = orgs
    _finding(hunt, a, "1")
    _finding(hunt, b, "2")

    inc_a = materialise_findings_for_org(hunt, a)
    inc_b = materialise_findings_for_org(hunt, b)

    assert inc_a != inc_b
    assert inc_a.organization == a
    assert inc_b.organization == b
    # each incident only carries its own org's alert
    assert Alert.objects.filter(incident=inc_a).count() == 1
    assert Alert.objects.filter(incident=inc_b).count() == 1
    # confirming A leaves B's proposal standing
    remaining = {p["organization_id"] for p in proposed_incidents(hunt)}
    assert remaining == set()  # both confirmed
