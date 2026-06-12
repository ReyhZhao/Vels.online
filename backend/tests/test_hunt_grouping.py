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
