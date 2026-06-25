"""Tests for Incident Reporting (PRD #618, ADR-0029).

Covers slices #619 (walking skeleton: generation service, renderer smoke, staff
API), #620 (audience-filtered grounding + Timeline + leak-safety), #621 (LLM
executive summary), #622 (Actions Taken + Recommendations), #623 (IOCs PAP ceiling
+ Asset Impact exposure omission), and #624 (customer-portal surfacing).
"""
from unittest.mock import MagicMock, patch

import pytest

from incidents.models import (
    Asset, Comment, IncidentAsset, IOC, Incident, IncidentEvent, NatExposure,
    Report, ReportTemplate, Task,
)
from incidents.services.report_grounding import build_report_grounding
from incidents.services.report_sections import render_section
from incidents.services.reports import (
    ReportGenerationError, generate_report, render_report_html,
)
from security.models import Organization, OrganizationMembership


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="sam", password="pass", is_staff=True
    )


@pytest.fixture
def member(db, django_user_model, acme):
    user = django_user_model.objects.create_user(username="mo", password="pass")
    OrganizationMembership.objects.create(user=user, organization=acme)
    return user


@pytest.fixture
def outsider(db, django_user_model):
    return django_user_model.objects.create_user(username="ozzy", password="pass")


def make_incident(org, n=1, tlp="green", pap="green", state="in_progress"):
    return Incident.objects.create(
        organization=org, title="Phishing wave", display_id=f"INC-2026-{n:04d}",
        tlp=tlp, pap=pap, state=state, severity="high", description="A phishing campaign.",
    )


def make_template(audience="customer", sections=None, **kwargs):
    return ReportTemplate.objects.create(
        organization=None,
        name=kwargs.pop("name", f"{audience} template"),
        audience=audience,
        sections=sections if sections is not None else ["incident_details"],
        **kwargs,
    )


@pytest.fixture
def fake_pdf():
    """Patch the PDF renderer + storage so service/API tests don't need WeasyPrint
    or real object storage. The dedicated smoke test exercises the real renderer."""
    with patch("incidents.services.reports.render_report_pdf", return_value=b"%PDF-1.4 fake"), \
         patch("incidents.services.reports.StorageClient") as Storage:
        Storage.return_value.upload_file = MagicMock()
        Storage.return_value.generate_presigned_url = MagicMock(return_value="https://dl/report.pdf")
        yield Storage


# ── grounding (#620): the leak-safety floor ─────────────────────────────────────


@pytest.mark.django_db
def test_grounding_internal_includes_internal_comments_and_events(acme):
    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="internal note", is_internal=True)
    Comment.objects.create(incident=inc, body="public note", is_internal=False)
    IncidentEvent.objects.create(incident=inc, kind="note", payload={"is_internal": True})
    IncidentEvent.objects.create(incident=inc, kind="opened", payload={})

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_INTERNAL)
    bodies = [c["body"] for c in g["comments"]]
    assert "internal note" in bodies and "public note" in bodies
    kinds = [e["kind"] for e in g["events"]]
    assert "note" in kinds and "opened" in kinds


@pytest.mark.django_db
def test_grounding_customer_excludes_internal_comments_and_events(acme):
    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="internal note", is_internal=True)
    Comment.objects.create(incident=inc, body="public note", is_internal=False)
    IncidentEvent.objects.create(incident=inc, kind="note", payload={"is_internal": True})
    IncidentEvent.objects.create(incident=inc, kind="opened", payload={})

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    bodies = [c["body"] for c in g["comments"]]
    assert bodies == ["public note"]
    kinds = [e["kind"] for e in g["events"]]
    assert "note" not in kinds and "opened" in kinds


@pytest.mark.django_db
def test_grounding_customer_at_amber_has_no_comments_or_events(acme):
    inc = make_incident(acme, tlp="amber")
    Comment.objects.create(incident=inc, body="public note", is_internal=False)
    IncidentEvent.objects.create(incident=inc, kind="opened", payload={})

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    assert g["comments"] == []
    assert g["events"] == []


# ── Timeline section (#620) ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_timeline_section_excludes_internal_events_for_customer(acme):
    inc = make_incident(acme, tlp="green")
    IncidentEvent.objects.create(incident=inc, kind="internal_only", payload={"is_internal": True})
    IncidentEvent.objects.create(incident=inc, kind="state_changed", payload={})

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    ctx = render_section("timeline", inc, g, make_template(audience="customer"))
    kinds = [e["kind"] for e in ctx["entries"]]
    assert "internal_only" not in kinds
    assert "state_changed" in kinds


@pytest.mark.django_db
def test_timeline_section_includes_internal_events_for_internal(acme):
    inc = make_incident(acme, tlp="green")
    IncidentEvent.objects.create(incident=inc, kind="internal_only", payload={"is_internal": True})
    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_INTERNAL)
    ctx = render_section("timeline", inc, g, make_template(audience="internal"))
    assert "internal_only" in [e["kind"] for e in ctx["entries"]]


# ── IOCs PAP ceiling (#623) ─────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("pap,suppressed", [("white", False), ("green", False), ("amber", True), ("red", True)])
def test_iocs_section_respects_pap_ceiling(acme, pap, suppressed):
    inc = make_incident(acme, tlp="green", pap=pap)
    IOC.objects.create(incident=inc, kind="ip", value="203.0.113.7")
    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_INTERNAL)
    ctx = render_section("iocs", inc, g, make_template())
    assert ctx["suppressed"] is suppressed
    if suppressed:
        assert ctx["indicators"] == []
    else:
        assert ctx["indicators"] == [{"kind": "ip", "value": "203.0.113.7"}]


# ── Asset Impact: exposure omission (#623) ──────────────────────────────────────


@pytest.mark.django_db
def test_asset_impact_lists_names_roles_only_no_exposure(acme):
    inc = make_incident(acme)
    asset = Asset.objects.create(
        organization=acme, kind="host", name="web01", agent_name="web01", role="web-server",
    )
    NatExposure.objects.create(asset=asset, protocol="tcp", port=443, description="https")
    IncidentAsset.objects.create(incident=inc, asset=asset)

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    ctx = render_section("asset_impact", inc, g, make_template())
    assert ctx["assets"] == [{"name": "web01", "role": "web-server", "kind": "host"}]
    # No exposure specifics anywhere in the rendered context.
    blob = str(ctx)
    for forbidden in ("443", "tcp", "https", "nat", "exposure"):
        assert forbidden not in blob.lower()


# ── Actions Taken (#622) ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_actions_taken_lists_completed_tasks_no_internal_comments(acme):
    inc = make_incident(acme)
    done = Task.objects.create(incident=inc, title="Block sender", state="done", task_type="wazuh_response")
    Task.objects.create(incident=inc, title="Open task", state="new", task_type="manual")
    Comment.objects.create(incident=inc, task=done, body="SECRET AI finding", is_internal=True)

    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    ctx = render_section("actions_taken", inc, g, make_template())
    titles = [a["title"] for a in ctx["actions"]]
    assert "Block sender" in titles
    assert "Open task" not in titles  # only completed tasks
    assert "SECRET AI finding" not in str(ctx)
    assert ctx["actions"][0]["type_label"] == "Wazuh Response"


# ── Recommendations (#622) ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_recommendations_renders_template_free_text(acme):
    inc = make_incident(acme)
    tmpl = make_template(recommendations_text="Rotate all credentials.")
    g = build_report_grounding(inc, ReportTemplate.AUDIENCE_CUSTOMER)
    ctx = render_section("recommendations", inc, g, tmpl)
    assert ctx["text"] == "Rotate all credentials."


# ── generation service (#619, #620) ─────────────────────────────────────────────


@pytest.mark.django_db
def test_generate_report_freezes_snapshot_fields(acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="green", state="resolved")
    tmpl = make_template(audience="customer", sections=["incident_details"], name="Customer Brief")
    report = generate_report(inc, tmpl, actor=staff)

    assert report.template_name == "Customer Brief"
    assert report.audience == "customer"
    assert report.tlp == "green"
    assert report.incident_state == "resolved"
    assert report.generated_by == staff
    assert report.reference_id.startswith("REP-")
    assert report.size_bytes > 0
    assert IncidentEvent.objects.filter(incident=inc, kind="report_generated").exists()


@pytest.mark.django_db
def test_report_survives_template_deletion(acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="green")
    tmpl = make_template(audience="internal", name="Internal Full")
    report = generate_report(inc, tmpl, actor=staff)
    tmpl.delete()
    report.refresh_from_db()
    assert report.template is None
    assert report.template_name == "Internal Full"
    assert report.audience == "internal"


@pytest.mark.django_db
def test_customer_report_refused_at_tlp_red(acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="red")
    tmpl = make_template(audience="customer")
    with pytest.raises(ReportGenerationError):
        generate_report(inc, tmpl, actor=staff)
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_staff_generated_customer_report_still_applies_customer_floor(acme, staff, fake_pdf):
    """A staff member generates a customer report; internal content must not leak in."""
    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="internal staff note", is_internal=True)
    IncidentEvent.objects.create(incident=inc, kind="internal_only", payload={"is_internal": True})
    tmpl = make_template(audience="customer", sections=["timeline"])
    report = generate_report(inc, tmpl, actor=staff)

    frozen = report.content["sections"][0]["context"]
    assert "internal_only" not in [e["kind"] for e in frozen["entries"]]


# ── executive summary (#621) ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_executive_summary_grounded_on_filtered_grounding_and_frozen(acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="internal staff note", is_internal=True)
    Comment.objects.create(incident=inc, body="public update", is_internal=False)
    tmpl = make_template(audience="customer", sections=["executive_summary"])

    captured = {}

    def fake_summary(grounding):
        captured["grounding"] = grounding
        return "A customer-safe summary."

    with patch("incidents.services.reports.generate_report_summary", side_effect=fake_summary):
        report = generate_report(inc, tmpl, actor=staff)

    # Fed only the audience-filtered grounding — no internal comment present.
    fed_bodies = [c["body"] for c in captured["grounding"]["comments"]]
    assert fed_bodies == ["public update"]
    # Output frozen into the immutable Report (no re-run on later views).
    assert report.executive_summary == "A customer-safe summary."
    assert report.content["sections"][0]["context"]["summary"] == "A customer-safe summary."


# ── renderer / PDF smoke (#619) ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_renderer_produces_nonempty_pdf_across_catalog_sections(acme, staff):
    """Smoke: a template using every catalog section renders to real PDF bytes."""
    inc = make_incident(acme, tlp="green", pap="green")
    asset = Asset.objects.create(organization=acme, kind="host", name="web01", agent_name="web01", role="server")
    IncidentAsset.objects.create(incident=inc, asset=asset)
    IOC.objects.create(incident=inc, kind="domain", value="evil.example")
    Task.objects.create(incident=inc, title="Contain host", state="done", task_type="manual")
    IncidentEvent.objects.create(incident=inc, kind="opened", payload={})

    tmpl = make_template(
        audience="internal",
        sections=["executive_summary", "incident_details", "timeline", "iocs", "actions_taken", "asset_impact", "recommendations"],
        recommendations_text="Patch and monitor.",
        intro_text="Intro.", outro_text="Outro.",
    )
    g = build_report_grounding(inc, "internal")
    g["executive_summary"] = "Summary prose."
    rendered = [
        {"kind": k, "title": k, "context": render_section(k, inc, g, tmpl)}
        for k in tmpl.sections
    ]
    from incidents.services.reports import render_report_pdf
    html = render_report_html(inc, tmpl, g, rendered)
    pdf = render_report_pdf(html)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


# ── staff API: generate / list / download (#619) ────────────────────────────────


@pytest.mark.django_db
def test_staff_create_template_generate_list_download(client, acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="green")
    client.force_login(staff)

    # create template
    resp = client.post(
        "/api/incidents/report-templates/",
        {"name": "Brief", "audience": "customer", "sections": ["incident_details"]},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    template_id = resp.json()["id"]

    # generate
    resp = client.post(
        f"/api/incidents/{inc.display_id}/reports/",
        {"template_id": template_id},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    report = resp.json()
    assert report["reference_id"].startswith("REP-")
    assert report["generated_by_username"] == "sam"

    # list
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # download
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/{report['id']}/download/")
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://dl/report.pdf"


@pytest.mark.django_db
def test_generate_report_requires_staff(client, acme, member, fake_pdf):
    inc = make_incident(acme, tlp="green")
    tmpl = make_template(audience="customer")
    client.force_login(member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/reports/",
        {"template_id": tmpl.id}, content_type="application/json",
    )
    assert resp.status_code == 403


# ── customer-portal surfacing (#624) ────────────────────────────────────────────


@pytest.mark.django_db
def test_org_member_sees_only_customer_reports(client, acme, staff, member, fake_pdf):
    inc = make_incident(acme, tlp="green")
    cust = generate_report(inc, make_template(audience="customer", name="C"), actor=staff)
    generate_report(inc, make_template(audience="internal", name="I"), actor=staff)

    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/")
    assert resp.status_code == 200
    data = resp.json()
    assert [r["reference_id"] for r in data] == [cust.reference_id]


@pytest.mark.django_db
def test_org_member_cannot_download_internal_report(client, acme, staff, member, fake_pdf):
    inc = make_incident(acme, tlp="green")
    internal = generate_report(inc, make_template(audience="internal"), actor=staff)
    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/{internal.id}/download/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_org_member_no_reports_on_tlp_red_incident(client, acme, staff, member, fake_pdf):
    inc = make_incident(acme, tlp="amber")
    rep = generate_report(inc, make_template(audience="customer"), actor=staff)
    # bump to red after generation; member can no longer view the incident at all
    inc.tlp = "red"
    inc.save(update_fields=["tlp"])
    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/")
    assert resp.status_code == 404
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/{rep.id}/download/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_staff_sees_both_audiences(client, acme, staff, fake_pdf):
    inc = make_incident(acme, tlp="green")
    generate_report(inc, make_template(audience="customer", name="C"), actor=staff)
    generate_report(inc, make_template(audience="internal", name="I"), actor=staff)
    client.force_login(staff)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/")
    assert len(resp.json()) == 2
