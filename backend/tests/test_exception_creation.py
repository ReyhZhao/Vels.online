import base64
import json
import pytest
from unittest.mock import MagicMock, patch

from security.models import Organization, OrganizationMembership
from incidents.models import Incident
from exceptions.models import ExceptionRule, WazuhRuleIdPool
from exceptions.services_xml import rule_file_path, rule_to_xml


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


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
def pool(db):
    obj, _ = WazuhRuleIdPool.objects.get_or_create(defaults={"last_assigned_id": 199999})
    obj.last_assigned_id = 199999
    obj.save()
    return obj


def make_rule(org=None, scope="org", wazuh_rule_id=200001, **kwargs):
    return ExceptionRule(
        wazuh_rule_id=wazuh_rule_id,
        trigger_rule_id=5763,
        description="Suppress login failures from web-01",
        scope=scope,
        organisation=org,
        status="applied",
        **kwargs,
    )


# ── XML assembly ─────────────────────────────────────────────────────────────


def test_xml_contains_rule_id(acme):
    rule = make_rule(acme)
    xml = rule_to_xml(rule)
    assert 'id="200001"' in xml
    assert 'level="0"' in xml


def test_xml_contains_description(acme):
    rule = make_rule(acme)
    xml = rule_to_xml(rule)
    assert "Suppress login failures from web-01" in xml


def test_xml_contains_if_sid(acme):
    rule = make_rule(acme)
    xml = rule_to_xml(rule)
    assert "<if_sid>5763</if_sid>" in xml


def test_xml_org_rule_with_agent_name_includes_agent_field(acme):
    rule = make_rule(acme, scope="org", agent_name="web-01")
    xml = rule_to_xml(rule)
    assert 'name="agent.name"' in xml
    assert "web-01" in xml


def test_xml_global_rule_omits_agent_field(acme):
    rule = make_rule(acme, scope="global", agent_name="web-01")
    xml = rule_to_xml(rule)
    assert 'name="agent.name"' not in xml


def test_xml_match_block_rendered(acme):
    rule = make_rule(acme, match_value="authentication failed")
    xml = rule_to_xml(rule)
    assert "<match>authentication failed</match>" in xml


def test_xml_field_block_rendered(acme):
    rule = make_rule(acme, field_name="srcuser", field_value="admin", field_type="literal")
    xml = rule_to_xml(rule)
    assert 'name="srcuser"' in xml
    assert "admin" in xml


def test_xml_no_match_block_when_empty(acme):
    rule = make_rule(acme)
    xml = rule_to_xml(rule)
    assert "<match>" not in xml


def test_rule_file_path_org_scoped(acme):
    rule = make_rule(acme, scope="org")
    assert rule_file_path(rule) == "rules/acme_exceptions.xml"


def test_rule_file_path_global():
    rule = make_rule(scope="global")
    assert rule_file_path(rule) == "rules/global_exceptions.xml"


def test_rule_file_path_no_org():
    rule = make_rule(scope="org")  # org=None
    assert rule_file_path(rule) == "rules/global_exceptions.xml"


# ── GitHub push service ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_push_rule_creates_new_file(acme):
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200001,
        trigger_rule_id=5763,
        description="Test rule",
        scope="org",
        organisation=acme,
        status="applied",
    )

    mock_get = MagicMock(status_code=404)
    mock_put = MagicMock(status_code=201)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import push_rule
        push_rule(rule)

    mock_put_call.assert_called_once()
    call_kwargs = mock_put_call.call_args
    payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
    content_decoded = base64.b64decode(payload["content"]).decode()
    assert "200001" in content_decoded
    assert "Test rule" in content_decoded


@pytest.mark.django_db
def test_push_rule_targets_org_file(acme):
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200002,
        description="Org rule",
        scope="org",
        organisation=acme,
        status="applied",
    )

    mock_get = MagicMock(status_code=404)
    mock_put = MagicMock(status_code=201)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import push_rule
        push_rule(rule)

    url = mock_put_call.call_args[0][0]
    assert "acme_exceptions.xml" in url


@pytest.mark.django_db
def test_push_rule_targets_global_file():
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200003,
        description="Global rule",
        scope="global",
        status="applied",
    )

    mock_get = MagicMock(status_code=404)
    mock_put = MagicMock(status_code=201)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import push_rule
        push_rule(rule)

    url = mock_put_call.call_args[0][0]
    assert "global_exceptions.xml" in url


# ── POST /api/exceptions/ ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_requires_auth(client, acme):
    response = client.post(
        "/api/exceptions/",
        {"org": "acme", "description": "Test"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_create_rejects_non_staff(client, acme_member, acme):
    client.force_login(acme_member)
    response = client.post(
        "/api/exceptions/",
        {"org": "acme", "description": "Test"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_staff_creates_rule_as_applied(admin_client, acme, pool):
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Test rule", "scope": "org"},
            content_type="application/json",
        )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "applied"
    assert data["org_slug"] == "acme"
    assert data["wazuh_rule_id"] == 200000


@pytest.mark.django_db
def test_create_allocates_id_from_pool(admin_client, acme, pool):
    with patch("exceptions.views.push_rule"):
        admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "First"},
            content_type="application/json",
        )
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Second"},
            content_type="application/json",
        )
    assert response.json()["wazuh_rule_id"] == 200001


@pytest.mark.django_db
def test_create_calls_push_rule(admin_client, acme, pool):
    with patch("exceptions.views.push_rule") as mock_push:
        admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Test"},
            content_type="application/json",
        )
    mock_push.assert_called_once()


@pytest.mark.django_db
def test_create_rule_saved_even_if_push_fails(admin_client, acme, pool):
    with patch("exceptions.views.push_rule", side_effect=RuntimeError("network error")):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Test"},
            content_type="application/json",
        )
    assert response.status_code == 201
    assert ExceptionRule.objects.filter(description="Test").exists()


@pytest.mark.django_db
def test_create_missing_org_returns_400(admin_client, pool):
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(
            "/api/exceptions/",
            {"description": "No org"},
            content_type="application/json",
        )
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_links_incident_when_provided(admin_client, acme, pool):
    incident = Incident.objects.create(
        display_id="INC-2026-0001",
        organization=acme,
        title="Test",
        source_kind="wazuh_event",
    )
    with patch("exceptions.views.push_rule"):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Linked", "incident": "INC-2026-0001"},
            content_type="application/json",
        )
    assert response.status_code == 201
    assert response.json()["incident_display_id"] == "INC-2026-0001"
