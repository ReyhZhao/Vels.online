"""Tests for #604: analyst add/edit/remove of incident IOCs."""
from unittest.mock import patch

import pytest

from incidents.models import IOC, Incident, IncidentEvent
from security.models import Organization, OrganizationMembership


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


def make_incident(org, n=1):
    return Incident.objects.create(
        organization=org, title="Test", display_id=f"INC-2026-{n:04d}", tlp="amber"
    )


# ── POST create ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_ioc_requires_auth(client, acme):
    inc = make_incident(acme)
    resp = client.post(f"/api/incidents/{inc.display_id}/iocs/", {}, content_type="application/json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_create_ioc_valid(client, acme_member, acme):
    inc = make_incident(acme)
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc"):
        resp = client.post(
            f"/api/incidents/{inc.display_id}/iocs/",
            {"kind": "ip", "value": "203.0.113.7"},
            content_type="application/json",
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "ip"
    assert data["value"] == "203.0.113.7"
    assert IOC.objects.filter(incident=inc, kind="ip", value="203.0.113.7").exists()
    assert IncidentEvent.objects.filter(incident=inc, kind="ioc_added", actor=acme_member).exists()


@pytest.mark.django_db
def test_create_ioc_invalid_kind(client, acme_member, acme):
    inc = make_incident(acme)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/iocs/",
        {"kind": "bogus", "value": "x"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert IOC.objects.filter(incident=inc).count() == 0


@pytest.mark.django_db
def test_create_ioc_empty_value(client, acme_member, acme):
    inc = make_incident(acme)
    client.force_login(acme_member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/iocs/",
        {"kind": "ip", "value": "   "},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert IOC.objects.filter(incident=inc).count() == 0


@pytest.mark.django_db
def test_create_ioc_duplicate_returns_400(client, acme_member, acme):
    inc = make_incident(acme)
    IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc"):
        resp = client.post(
            f"/api/incidents/{inc.display_id}/iocs/",
            {"kind": "ip", "value": "203.0.113.7"},
            content_type="application/json",
        )
    assert resp.status_code == 400
    assert IOC.objects.filter(incident=inc, kind="ip", value="203.0.113.7").count() == 1


@pytest.mark.django_db
def test_create_ioc_enrichment_dispatched(client, acme_member, acme, django_capture_on_commit_callbacks):
    inc = make_incident(acme)
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc") as mock_task:
        with django_capture_on_commit_callbacks(execute=True):
            resp = client.post(
                f"/api/incidents/{inc.display_id}/iocs/",
                {"kind": "ip", "value": "203.0.113.7"},
                content_type="application/json",
            )
    assert resp.status_code == 201
    ioc = IOC.objects.get(incident=inc, value="203.0.113.7")
    mock_task.delay.assert_called_once_with(ioc.id)


@pytest.mark.django_db
def test_create_ioc_no_access(client, alice, acme, contoso):
    inc = make_incident(acme)
    OrganizationMembership.objects.create(user=alice, organization=contoso)
    client.force_login(alice)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/iocs/",
        {"kind": "ip", "value": "203.0.113.7"},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert IOC.objects.filter(incident=inc).count() == 0


# ── GET list ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_iocs(client, acme_member, acme):
    inc = make_incident(acme)
    IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    IOC.objects.create(incident=inc, kind="domain", value="evil.com")
    client.force_login(acme_member)
    resp = client.get(f"/api/incidents/{inc.display_id}/iocs/")
    assert resp.status_code == 200
    values = {row["value"] for row in resp.json()}
    assert values == {"203.0.113.7", "evil.com"}


# ── PATCH update ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_update_ioc_value(client, acme_member, acme):
    inc = make_incident(acme)
    ioc = IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc"):
        resp = client.patch(
            f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/",
            {"value": "198.51.100.4"},
            content_type="application/json",
        )
    assert resp.status_code == 200
    ioc.refresh_from_db()
    assert ioc.value == "198.51.100.4"
    assert IncidentEvent.objects.filter(incident=inc, kind="ioc_updated", actor=acme_member).exists()


@pytest.mark.django_db
def test_update_ioc_clears_stale_enrichment(client, acme_member, acme):
    inc = make_incident(acme)
    ioc = IOC.objects.create(
        incident=inc, kind="ip", value="203.0.113.7",
        enrichment_data={"abuseipdb": {"status": "done", "abuse_confidence_score": 90}},
    )
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc"):
        resp = client.patch(
            f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/",
            {"value": "198.51.100.4"},
            content_type="application/json",
        )
    assert resp.status_code == 200
    ioc.refresh_from_db()
    assert ioc.enrichment_data == {}


@pytest.mark.django_db
def test_update_ioc_reenriches_on_change(client, acme_member, acme, django_capture_on_commit_callbacks):
    inc = make_incident(acme)
    ioc = IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    client.force_login(acme_member)
    with patch("incidents.views.enrich_single_ioc") as mock_task:
        with django_capture_on_commit_callbacks(execute=True):
            resp = client.patch(
                f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/",
                {"value": "198.51.100.4"},
                content_type="application/json",
            )
    assert resp.status_code == 200
    mock_task.delay.assert_called_once_with(ioc.id)


@pytest.mark.django_db
def test_update_ioc_collision_returns_400(client, acme_member, acme):
    inc = make_incident(acme)
    IOC.objects.create(incident=inc, kind="ip", value="198.51.100.4")
    ioc = IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    client.force_login(acme_member)
    resp = client.patch(
        f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/",
        {"value": "198.51.100.4"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    ioc.refresh_from_db()
    assert ioc.value == "203.0.113.7"


# ── DELETE ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_ioc(client, acme_member, acme):
    inc = make_incident(acme)
    ioc = IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    client.force_login(acme_member)
    resp = client.delete(f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/")
    assert resp.status_code == 204
    assert not IOC.objects.filter(id=ioc.id).exists()
    assert IncidentEvent.objects.filter(incident=inc, kind="ioc_removed", actor=acme_member).exists()


@pytest.mark.django_db
def test_delete_ioc_no_access(client, alice, acme, contoso):
    inc = make_incident(acme)
    ioc = IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    OrganizationMembership.objects.create(user=alice, organization=contoso)
    client.force_login(alice)
    resp = client.delete(f"/api/incidents/{inc.display_id}/iocs/{ioc.id}/")
    assert resp.status_code == 404
    assert IOC.objects.filter(id=ioc.id).exists()
