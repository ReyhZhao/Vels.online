import pytest
from unittest.mock import patch

from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent
from exceptions.models import ExceptionRule, WazuhRuleIdPool


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(
        display_id="INC-2026-0001",
        organization=acme,
        title="Test Incident",
        source_kind="wazuh_event",
    )


@pytest.fixture
def pool(db):
    obj, _ = WazuhRuleIdPool.objects.get_or_create(defaults={"last_assigned_id": 199999})
    obj.last_assigned_id = 199999
    obj.save()
    return obj


@pytest.fixture
def applied_rule(db, acme, incident):
    return ExceptionRule.objects.create(
        wazuh_rule_id=200001,
        description="Applied rule",
        scope="org",
        organisation=acme,
        incident=incident,
        status="applied",
    )


# ── creation writes timeline event ────────────────────────────────────────────


@pytest.mark.django_db
def test_create_exception_writes_timeline_event(admin_client, acme, incident, pool):
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Suppress brute force", "incident": "INC-2026-0001", "trigger_rule_id": 100200},
            content_type="application/json",
        )
    assert response.status_code == 201
    events = IncidentEvent.objects.filter(incident=incident, kind="exception_created")
    assert events.count() == 1
    event = events.first()
    assert event.payload["description"] == "Suppress brute force"
    assert "rule_id" in event.payload
    assert "wazuh_rule_id" in event.payload


@pytest.mark.django_db
def test_create_exception_without_incident_writes_no_event(admin_client, acme, pool):
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "No incident linked", "trigger_rule_id": 100201},
            content_type="application/json",
        )
    assert response.status_code == 201
    assert IncidentEvent.objects.filter(kind="exception_created").count() == 0


@pytest.mark.django_db
def test_approve_does_not_write_timeline_event(admin_client, applied_rule, incident):
    pending_rule = ExceptionRule.objects.create(
        wazuh_rule_id=200002,
        description="Pending",
        scope="org",
        organisation=applied_rule.organisation,
        incident=incident,
        status="pending",
    )
    with patch("exceptions.views.push_rule"):
        admin_client.post(f"/api/exceptions/{pending_rule.pk}/approve/")
    assert IncidentEvent.objects.filter(incident=incident, kind="exception_created").count() == 0


@pytest.mark.django_db
def test_disable_does_not_write_timeline_event(admin_client, acme, incident, pool):
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200005,
        description="Applied",
        scope="org",
        organisation=acme,
        incident=incident,
        status="applied",
    )
    with patch("exceptions.views.remove_rule"):
        admin_client.post(f"/api/exceptions/{rule.pk}/disable/")
    assert IncidentEvent.objects.filter(incident=incident, kind="exception_created").count() == 0


# ── timeline endpoint includes exception_created event ───────────────────────


@pytest.mark.django_db
def test_timeline_includes_exception_created_event(admin_client, acme, incident, pool):
    with patch("exceptions.views.push_rule"):
        admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Timeline test", "incident": "INC-2026-0001", "trigger_rule_id": 100202},
            content_type="application/json",
        )
    response = admin_client.get(f"/api/incidents/{incident.display_id}/timeline/")
    assert response.status_code == 200
    kinds = [e["kind"] for e in response.json()["results"]]
    assert "exception_created" in kinds


# ── incident filter on GET /api/exceptions/ ──────────────────────────────────


@pytest.mark.django_db
def test_list_filter_by_incident(admin_client, acme, incident):
    other_incident = Incident.objects.create(
        display_id="INC-2026-0002",
        organization=acme,
        title="Other",
        source_kind="wazuh_event",
    )
    ExceptionRule.objects.create(
        wazuh_rule_id=200010, description="Rule A", scope="org",
        organisation=acme, incident=incident, status="applied",
    )
    ExceptionRule.objects.create(
        wazuh_rule_id=200011, description="Rule B", scope="org",
        organisation=acme, incident=other_incident, status="applied",
    )
    ExceptionRule.objects.create(
        wazuh_rule_id=200012, description="Rule C", scope="org",
        organisation=acme, status="applied",
    )

    response = admin_client.get(f"/api/exceptions/?incident={incident.display_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["description"] == "Rule A"


@pytest.mark.django_db
def test_member_can_filter_by_own_incident(client, acme, incident):
    member = __import__("django").contrib.auth.get_user_model().objects.create_user(
        username="alice", password="pass"
    )
    OrganizationMembership.objects.create(user=member, organization=acme)
    ExceptionRule.objects.create(
        wazuh_rule_id=200013, description="Org rule", scope="org",
        organisation=acme, incident=incident, status="applied",
    )
    client.force_login(member)
    response = client.get(f"/api/exceptions/?incident={incident.display_id}")
    assert response.status_code == 200
    assert len(response.json()) == 1
