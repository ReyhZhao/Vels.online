"""Tests for the v2 alert ingestion endpoint (entity envelope required)."""
import pytest
from django.contrib.auth.models import User
from security.models import Organization, OrganizationMembership
from alerts.models import Alert, AlertEntity


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass", is_staff=False)


@pytest.fixture
def member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


def _base_payload(org="acme"):
    return {
        "source_kind": "wazuh_event",
        "source_ref": {
            "rule_id": "100002",
            "rule_description": "Lateral movement detected",
            "agent_name": "web-01",
            "level": 9,
        },
        "org": org,
    }


V2_URL = "/api/v2/alerts/"


# ---------------------------------------------------------------------------
# Envelope-required validation
# ---------------------------------------------------------------------------

class TestV2EnvelopeRequired:
    def test_missing_envelope_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        resp = client.post(V2_URL, _base_payload(), content_type="application/json")
        assert resp.status_code == 422
        assert "entities" in resp.json()["detail"]

    def test_null_envelope_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": None}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 422

    def test_non_dict_envelope_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": "host.name=web-01"}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 422

    def test_empty_dict_envelope_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 422

    def test_envelope_with_only_unknown_keys_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {"host.group": "dmz", "cloud.region": "us-east-1"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 422
        assert "host.name" in resp.json()["detail"]

    def test_envelope_with_only_empty_values_returns_422(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {"host.name": "", "user.name": ""}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Valid envelope — accepted
# ---------------------------------------------------------------------------

class TestV2ValidEnvelope:
    def test_valid_envelope_creates_alert(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {"host.name": "web-01"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_id"].startswith("AL-")
        assert data["source_kind"] == "wazuh_event"

    def test_valid_envelope_persists_entity_rows(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {"host.name": "WEB-PROD-01", "user.name": "CORP\\alice"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 201
        alert = Alert.objects.get(display_id=resp.json()["display_id"])
        entities = {e.entity_type: e.value for e in AlertEntity.objects.filter(alert=alert)}
        assert entities["host.name"] == "web-prod-01"
        assert entities["user.name"] == "alice"

    def test_unknown_ecs_keys_silently_ignored_when_valid_key_present(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(), "entities": {"host.name": "web-01", "host.group": "dmz"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 201
        alert = Alert.objects.get(display_id=resp.json()["display_id"])
        ents = AlertEntity.objects.filter(alert=alert)
        assert ents.count() == 1
        assert ents.first().entity_type == "host.name"

    def test_all_five_ecs_fields_accepted(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {
            **_base_payload(),
            "entities": {
                "host.name": "web-01",
                "source.ip": "1.2.3.4",
                "user.name": "alice",
                "file.hash.sha256": "a" * 64,
                "process.name": "svchost.exe",
            },
        }
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 201
        alert = Alert.objects.get(display_id=resp.json()["display_id"])
        assert AlertEntity.objects.filter(alert=alert).count() == 5

    def test_workflow_alert_with_envelope_accepted(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {
            "source_kind": "workflow",
            "source_ref": {},
            "org": "acme",
            "title": "Suspicious login",
            "entities": {"source.ip": "10.0.0.1"},
        }
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Auth / permission pass-through (same as v1)
# ---------------------------------------------------------------------------

class TestV2AuthPassthrough:
    def test_unauthenticated_returns_401(self, client, acme):
        payload = {**_base_payload(), "entities": {"host.name": "web-01"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 401

    def test_non_staff_returns_403(self, client, member, acme):
        client.force_login(member)
        payload = {**_base_payload(), "entities": {"host.name": "web-01"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 403

    def test_unknown_org_returns_404(self, client, staff_user, acme):
        client.force_login(staff_user)
        payload = {**_base_payload(org="no-such-org"), "entities": {"host.name": "web-01"}}
        resp = client.post(V2_URL, payload, content_type="application/json")
        assert resp.status_code == 404
