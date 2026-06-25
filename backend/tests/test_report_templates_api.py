"""Tests for staff Report Template authoring API (PRD #626, ADR-0029).

Templates are global (organization = null) and staff-only. The catalog of section
kinds is server-defined; ordering persists and is honored at render time.
"""
from unittest.mock import MagicMock, patch

import pytest

from incidents.models import Incident, Report, ReportTemplate
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="sam", password="pass", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    user = django_user_model.objects.create_user(username="mo", password="pass")
    OrganizationMembership.objects.create(user=user, organization=acme)
    return user


# ── access control / global+staff-only ──────────────────────────────────────────


@pytest.mark.django_db
def test_template_crud_requires_staff(client, member):
    client.force_login(member)
    assert client.get("/api/incidents/report-templates/").status_code == 403
    resp = client.post(
        "/api/incidents/report-templates/",
        {"name": "x", "audience": "customer", "sections": []},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_catalog_lists_server_defined_section_kinds(client, staff):
    client.force_login(staff)
    resp = client.get("/api/incidents/report-sections/")
    assert resp.status_code == 200
    kinds = [s["kind"] for s in resp.json()]
    assert "executive_summary" in kinds and "incident_details" in kinds and "iocs" in kinds


# ── CRUD incl. section ordering + audience ───────────────────────────────────────


@pytest.mark.django_db
def test_create_template_persists_section_order_and_audience(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/incidents/report-templates/",
        {
            "name": "Full Internal",
            "audience": "internal",
            "sections": ["timeline", "incident_details", "iocs"],
            "recommendations_text": "Do the needful.",
        },
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    tmpl = ReportTemplate.objects.get(pk=resp.json()["id"])
    assert tmpl.organization is None  # global
    assert tmpl.audience == "internal"
    assert tmpl.sections == ["timeline", "incident_details", "iocs"]
    assert tmpl.created_by == staff


@pytest.mark.django_db
def test_create_template_rejects_unknown_section_kind(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/incidents/report-templates/",
        {"name": "Bad", "audience": "customer", "sections": ["not_a_section"]},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_edit_template_reorders_sections(client, staff):
    tmpl = ReportTemplate.objects.create(
        organization=None, name="T", audience="customer",
        sections=["incident_details", "timeline"],
    )
    client.force_login(staff)
    resp = client.patch(
        f"/api/incidents/report-templates/{tmpl.id}/",
        {"sections": ["timeline", "incident_details"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    tmpl.refresh_from_db()
    assert tmpl.sections == ["timeline", "incident_details"]


@pytest.mark.django_db
def test_delete_template(client, staff):
    tmpl = ReportTemplate.objects.create(organization=None, name="T", audience="customer", sections=[])
    client.force_login(staff)
    resp = client.delete(f"/api/incidents/report-templates/{tmpl.id}/")
    assert resp.status_code == 204
    assert not ReportTemplate.objects.filter(pk=tmpl.id).exists()


# ── ordering honored at render time ─────────────────────────────────────────────


@pytest.mark.django_db
def test_section_order_reflected_in_generated_report(acme, staff):
    from incidents.services.reports import generate_report

    inc = Incident.objects.create(
        organization=acme, title="X", display_id="INC-2026-0700",
        tlp="green", pap="green", state="in_progress",
    )
    tmpl = ReportTemplate.objects.create(
        organization=None, name="Ordered", audience="internal",
        sections=["asset_impact", "incident_details", "timeline"],
    )
    with patch("incidents.services.reports.render_report_pdf", return_value=b"%PDF-1.4 x"), \
         patch("incidents.services.reports.StorageClient") as Storage:
        Storage.return_value.upload_file = MagicMock()
        report = generate_report(inc, tmpl, actor=staff)

    rendered_kinds = [s["kind"] for s in report.content["sections"]]
    assert rendered_kinds == ["asset_impact", "incident_details", "timeline"]
