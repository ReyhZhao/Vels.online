import base64
import json
import xml.etree.ElementTree as ET
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
    assert rule_file_path(rule) == "wazuh/files/rules/acme_exceptions.xml"


def test_rule_file_path_global():
    rule = make_rule(scope="global")
    assert rule_file_path(rule) == "wazuh/files/rules/global_exceptions.xml"


def test_rule_file_path_no_org():
    rule = make_rule(scope="org")  # org=None
    assert rule_file_path(rule) == "wazuh/files/rules/global_exceptions.xml"


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


# ── apps-values.yaml volume mount injection ───────────────────────────────────

_SAMPLE_VALUES_YAML = """\
wazuh:
  wazuh:
    master:
      additionalVolumes:
        - name: dynamic-rule-config
          configMap:
            name: rules-configmap
      additionalVolumeMounts:
        - name: dynamic-rule-config
          mountPath: /wazuh-config-mount/etc/rules/custom_rules.xml
          subPath: custom_rules.xml
    worker:
      annotations:
        #reloader.stakater.com/auto: "true"
        configmap.reloader.stakater.com/reload: "rules-configmap"
"""


def _make_values_get_response(yaml_content: str):
    """Return a mock GET response for the apps-values.yaml file."""
    encoded = base64.b64encode(yaml_content.encode()).decode()
    mock = MagicMock(status_code=200)
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"content": encoded, "sha": "abc123"}
    return mock


@pytest.mark.django_db
def test_push_rule_calls_ensure_volume_mount_for_new_file(acme):
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200010,
        description="New file rule",
        scope="org",
        organisation=acme,
        status="applied",
    )

    mock_404 = MagicMock(status_code=404)
    mock_put = MagicMock(status_code=201)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_404), \
         patch("exceptions.services_github.requests.put", return_value=mock_put), \
         patch("exceptions.services_github._ensure_volume_mount") as mock_ensure:
        from exceptions.services_github import push_rule
        push_rule(rule)

    mock_ensure.assert_called_once_with("wazuh/files/rules/acme_exceptions.xml")


@pytest.mark.django_db
def test_push_rule_skips_ensure_volume_mount_for_existing_file(acme):
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200011,
        description="Existing file rule",
        scope="org",
        organisation=acme,
        status="applied",
    )

    existing_content = base64.b64encode(b"<group></group>").decode()
    mock_200 = MagicMock(status_code=200)
    mock_200.raise_for_status = MagicMock()
    mock_200.json.return_value = {"content": existing_content, "sha": "existingsha"}
    mock_put = MagicMock(status_code=200)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_200), \
         patch("exceptions.services_github.requests.put", return_value=mock_put), \
         patch("exceptions.services_github._ensure_volume_mount") as mock_ensure:
        from exceptions.services_github import push_rule
        push_rule(rule)

    mock_ensure.assert_not_called()


def test_ensure_volume_mount_adds_to_master():
    mock_get = _make_values_get_response(_SAMPLE_VALUES_YAML)
    mock_put = MagicMock(status_code=200)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import _ensure_volume_mount
        _ensure_volume_mount("wazuh/files/rules/acme_exceptions.xml")

    mock_put_call.assert_called_once()
    payload = mock_put_call.call_args[1]["json"]
    assert payload["sha"] == "abc123"
    assert "acme_exceptions.xml" in payload["message"]

    updated_yaml = base64.b64decode(payload["content"]).decode()
    from ruamel.yaml import YAML
    ryaml = YAML()
    data = ryaml.load(updated_yaml)
    master = data["wazuh"]["wazuh"]["master"]
    assert any(m["subPath"] == "acme_exceptions.xml" for m in master["additionalVolumeMounts"])
    assert "#reloader.stakater.com/auto" in updated_yaml  # comment preserved


def test_ensure_volume_mount_does_not_touch_worker():
    mock_get = _make_values_get_response(_SAMPLE_VALUES_YAML)
    mock_put = MagicMock(status_code=200)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import _ensure_volume_mount
        _ensure_volume_mount("wazuh/files/rules/acme_exceptions.xml")

    updated_yaml = base64.b64decode(mock_put_call.call_args[1]["json"]["content"]).decode()
    from ruamel.yaml import YAML
    ryaml = YAML()
    data = ryaml.load(updated_yaml)
    worker = data["wazuh"]["wazuh"]["worker"]
    assert "additionalVolumeMounts" not in worker


def test_ensure_volume_mount_idempotent_when_already_present():
    yaml_with_entry = """\
wazuh:
  wazuh:
    master:
      additionalVolumes:
        - name: dynamic-rule-config
          configMap:
            name: rules-configmap
      additionalVolumeMounts:
        - name: dynamic-rule-config
          mountPath: /wazuh-config-mount/etc/rules/custom_rules.xml
          subPath: custom_rules.xml
        - name: dynamic-rule-config
          mountPath: /wazuh-config-mount/etc/rules/acme_exceptions.xml
          subPath: acme_exceptions.xml
    worker:
      annotations:
        configmap.reloader.stakater.com/reload: "rules-configmap"
"""
    mock_get = _make_values_get_response(yaml_with_entry)
    mock_put = MagicMock(status_code=200)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import _ensure_volume_mount
        _ensure_volume_mount("wazuh/files/rules/acme_exceptions.xml")

    mock_put_call.assert_not_called()


def test_ensure_volume_mount_does_nothing_when_values_file_missing():
    mock_404 = MagicMock(status_code=404)
    mock_put = MagicMock(status_code=200)

    with patch("exceptions.services_github.requests.get", return_value=mock_404), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import _ensure_volume_mount
        _ensure_volume_mount("wazuh/files/rules/acme_exceptions.xml")

    mock_put_call.assert_not_called()


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
            {"org": "acme", "description": "Test rule", "scope": "org", "trigger_rule_id": 100200},
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
            {"org": "acme", "description": "First", "trigger_rule_id": 100201},
            content_type="application/json",
        )
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Second", "trigger_rule_id": 100202},
            content_type="application/json",
        )
    assert response.json()["wazuh_rule_id"] == 200001


@pytest.mark.django_db
def test_create_calls_push_rule(admin_client, acme, pool):
    with patch("exceptions.views.push_rule") as mock_push:
        admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Test", "trigger_rule_id": 100203},
            content_type="application/json",
        )
    mock_push.assert_called_once()


@pytest.mark.django_db
def test_create_rule_push_failure_returns_502_and_rolls_back(admin_client, acme, pool):
    with patch("exceptions.views.push_rule", side_effect=RuntimeError("network error")):
        response = admin_client.post(
            "/api/exceptions/",
            {"org": "acme", "description": "Test", "trigger_rule_id": 100204},
            content_type="application/json",
        )
    assert response.status_code == 502
    assert not ExceptionRule.objects.filter(description="Test").exists()


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
            {"org": "acme", "description": "Linked", "incident": "INC-2026-0001", "trigger_rule_id": 100205},
            content_type="application/json",
        )
    assert response.status_code == 201
    assert response.json()["incident_display_id"] == "INC-2026-0001"


# ── Resilience to unparseable existing files (#650) ──────────────────────────

# The real velsonline_exceptions.xml had its entire body wrapped in an XML
# comment, so ET.fromstring raised "no element found: line 13, column 12" and
# every exception push 502'd. The assembler must treat such content as empty.
COMMENTED_OUT_FILE = """<!-- <group name="exceptions">
  <rule id="200006" level="0">
    <description>Suppress netstat change alerts on this development machine.</description>
    <if_sid>533</if_sid>
    <field name="agent.name">MacbookPro-M5</field>
  </rule>
  <rule id="200013" level="0">
    <description>Ignore legitimate OneDriveStandaloneUpdater.exe on eddie-pc</description>
    <if_sid>111202</if_sid>
    <field name="agent.name">eddie-pc</field>
  </rule>
</group> -->"""


def test_upsert_into_comment_only_file_does_not_raise():
    from exceptions.services_github import _upsert_rule_element

    rule_xml = '<rule id="200020" level="0"><description>New</description></rule>'
    result = _upsert_rule_element(COMMENTED_OUT_FILE, rule_xml, 200020, "velsonline_exceptions.xml")

    # Result must be a valid, single-rooted <group> containing only the new rule
    root = ET.fromstring(result)
    assert root.tag == "group"
    assert [r.get("id") for r in root.findall("rule")] == ["200020"]


def test_upsert_into_empty_file_still_works():
    from exceptions.services_github import _upsert_rule_element

    rule_xml = '<rule id="200021" level="0"><description>New</description></rule>'
    result = _upsert_rule_element("   \n  ", rule_xml, 200021)
    root = ET.fromstring(result)
    assert [r.get("id") for r in root.findall("rule")] == ["200021"]


def test_upsert_into_valid_file_preserves_other_rules():
    from exceptions.services_github import _upsert_rule_element

    existing = (
        '<group name="exceptions">'
        '<rule id="200007" level="0"><description>Keep me</description></rule>'
        '</group>'
    )
    rule_xml = '<rule id="200022" level="0"><description>New</description></rule>'
    result = _upsert_rule_element(existing, rule_xml, 200022)
    root = ET.fromstring(result)
    ids = sorted(r.get("id") for r in root.findall("rule"))
    assert ids == ["200007", "200022"]


def test_remove_from_comment_only_file_does_not_raise():
    from exceptions.services_github import _remove_rule_element

    result = _remove_rule_element(COMMENTED_OUT_FILE, 200006, "velsonline_exceptions.xml")
    root = ET.fromstring(result)
    assert root.tag == "group"
    assert root.findall("rule") == []


@pytest.mark.django_db
def test_push_rule_succeeds_when_existing_file_is_commented_out(acme):
    """End-to-end: pushing when the org file body is fully commented out must
    not raise ParseError and must PUT a clean single-rooted group (#650)."""
    rule = ExceptionRule.objects.create(
        wazuh_rule_id=200030,
        trigger_rule_id=5763,
        description="Recover from commented-out file",
        scope="org",
        organisation=acme,
        status="applied",
    )

    mock_get = MagicMock(status_code=200)
    mock_get.json.return_value = {
        "content": base64.b64encode(COMMENTED_OUT_FILE.encode()).decode(),
        "sha": "abc123",
    }
    mock_get.raise_for_status = MagicMock()
    mock_put = MagicMock(status_code=200)
    mock_put.raise_for_status = MagicMock()

    with patch("exceptions.services_github.requests.get", return_value=mock_get), \
         patch("exceptions.services_github.requests.put", return_value=mock_put) as mock_put_call:
        from exceptions.services_github import push_rule
        push_rule(rule)

    payload = mock_put_call.call_args[1]["json"]
    content_decoded = base64.b64decode(payload["content"]).decode()
    root = ET.fromstring(content_decoded)  # must parse — no ParseError
    assert "200030" in content_decoded
    assert root.tag == "group"
