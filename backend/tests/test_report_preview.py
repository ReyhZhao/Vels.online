"""Tests for the Report Preview feature (PRD #632).

Covers slice #636 (rich-text rendering), #638 (per-Report overrides at generate),
#635 (preview scaffold + report_preview), and #637 (on-demand summary endpoint).
Assertions are on external behaviour: what renders, what is (not) persisted, what
the Audience floor lets through.
"""
from unittest.mock import MagicMock, patch

import pytest

from incidents.models import Comment, Incident, Report, ReportTemplate
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
    """Patch the PDF renderer + storage so service/API tests don't need WeasyPrint."""
    with patch("incidents.services.reports.render_report_pdf", return_value=b"%PDF-1.4 fake"), \
         patch("incidents.services.reports.StorageClient") as Storage:
        Storage.return_value.upload_file = MagicMock()
        Storage.return_value.generate_presigned_url = MagicMock(return_value="https://dl/r.pdf")
        yield Storage


# ── slice #636: rich-text rendering ─────────────────────────────────────────────


@pytest.mark.django_db
def test_template_richtext_renders_as_markup_in_report_html(acme):
    from incidents.services.report_grounding import build_report_grounding
    from incidents.services.reports import render_report_html

    inc = make_incident(acme)
    tmpl = make_template(
        audience="internal",
        sections=["recommendations"],
        intro_text="<p>Hello <strong>team</strong></p>",
        recommendations_text="<ul><li>Patch now</li></ul>",
    )
    g = build_report_grounding(inc, tmpl.audience)
    from incidents.services.report_sections import render_section, SECTION_TITLES
    rendered = [
        {"kind": k, "title": SECTION_TITLES.get(k, k),
         "context": render_section(k, inc, g, tmpl)}
        for k in tmpl.sections
    ]
    html = render_report_html(inc, tmpl, g, rendered)
    assert "<strong>team</strong>" in html
    assert "<ul><li>Patch now</li></ul>" in html


@pytest.mark.django_db
def test_richtext_rendering_strips_dangerous_markup(acme):
    from incidents.services.report_grounding import build_report_grounding
    from incidents.services.reports import render_report_html

    inc = make_incident(acme)
    tmpl = make_template(
        audience="internal", sections=["incident_details"],
        intro_text='<p onclick="x">hi</p><script>alert(1)</script>',
    )
    g = build_report_grounding(inc, tmpl.audience)
    html = render_report_html(inc, tmpl, g, [])
    assert "onclick" not in html
    assert "alert(1)" not in html
    assert "<p>hi</p>" in html


@pytest.mark.django_db
def test_executive_summary_is_sanitized_at_render(acme):
    from incidents.services.report_grounding import build_report_grounding
    from incidents.services.reports import render_report_html

    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["executive_summary"])
    g = build_report_grounding(inc, tmpl.audience)
    g["executive_summary"] = "<p>Summary</p><script>steal()</script>"
    from incidents.services.report_sections import render_section, SECTION_TITLES
    rendered = [{
        "kind": "executive_summary", "title": SECTION_TITLES["executive_summary"],
        "context": render_section("executive_summary", inc, g, tmpl),
    }]
    html = render_report_html(inc, tmpl, g, rendered)
    assert "<p>Summary</p>" in html
    assert "steal()" not in html
    assert "<script" not in html


# ── slice #638: per-Report overrides at generate ────────────────────────────────


@pytest.mark.django_db
def test_override_freezes_into_report_content(acme, staff, fake_pdf):
    from incidents.services.reports import generate_report

    inc = make_incident(acme)
    tmpl = make_template(
        audience="internal", sections=["recommendations"],
        intro_text="<p>template intro</p>", recommendations_text="<p>template rec</p>",
    )
    report = generate_report(
        inc, tmpl, actor=staff,
        overrides={
            "intro_text": "<p>tailored <strong>intro</strong></p>",
            "recommendations_text": "<ul><li>do this</li></ul>",
        },
    )
    assert report.content["intro_text"] == "<p>tailored <strong>intro</strong></p>"
    assert report.content["recommendations_text"] == "<ul><li>do this</li></ul>"
    # outro not overridden → template default
    assert report.content["outro_text"] == tmpl.outro_text


@pytest.mark.django_db
def test_supplied_summary_is_verbatim_and_skips_llm(acme, staff, fake_pdf):
    from incidents.services.reports import generate_report

    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["executive_summary"])
    with patch("incidents.services.reports.generate_report_summary") as llm:
        report = generate_report(
            inc, tmpl, actor=staff,
            overrides={"executive_summary": "<p>Analyst-written summary</p>"},
        )
    llm.assert_not_called()
    assert report.executive_summary == "<p>Analyst-written summary</p>"


@pytest.mark.django_db
def test_absent_summary_generates_via_llm(acme, staff, fake_pdf):
    from incidents.services.reports import generate_report

    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["executive_summary"])
    with patch("incidents.services.reports.generate_report_summary",
               return_value="<p>AI summary</p>") as llm:
        report = generate_report(inc, tmpl, actor=staff, overrides={})
    llm.assert_called_once()
    assert report.executive_summary == "<p>AI summary</p>"


@pytest.mark.django_db
def test_overrides_never_mutate_template(acme, staff, fake_pdf):
    from incidents.services.reports import generate_report

    inc = make_incident(acme)
    tmpl = make_template(
        audience="internal", sections=["recommendations"],
        intro_text="<p>orig</p>", recommendations_text="<p>orig rec</p>",
    )
    generate_report(
        inc, tmpl, actor=staff,
        overrides={"intro_text": "<p>changed</p>", "recommendations_text": "<p>changed</p>"},
    )
    tmpl.refresh_from_db()
    assert tmpl.intro_text == "<p>orig</p>"
    assert tmpl.recommendations_text == "<p>orig rec</p>"


@pytest.mark.django_db
def test_dirty_override_is_sanitized_at_generate(acme, staff, fake_pdf):
    from incidents.services.reports import generate_report

    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["incident_details"])
    report = generate_report(
        inc, tmpl, actor=staff,
        overrides={"intro_text": '<p onclick="x">hi</p><script>bad()</script>'},
    )
    assert "onclick" not in report.content["intro_text"]
    assert "bad()" not in report.content["intro_text"]
    assert "<p>hi</p>" in report.content["intro_text"]


@pytest.mark.django_db
def test_customer_override_on_red_still_refused(acme, staff, fake_pdf):
    from incidents.services.reports import ReportGenerationError, generate_report

    inc = make_incident(acme, tlp="red")
    tmpl = make_template(audience="customer", sections=["incident_details"])
    with pytest.raises(ReportGenerationError):
        generate_report(inc, tmpl, actor=staff, overrides={"intro_text": "<p>x</p>"})


@pytest.mark.django_db
def test_generate_endpoint_accepts_overrides(client, acme, staff, fake_pdf):
    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["recommendations"])
    client.force_login(staff)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/reports/",
        {"template_id": tmpl.id, "recommendations_text": "<ul><li>patch</li></ul>"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    rep = Report.objects.get(pk=resp.json()["id"])
    assert rep.content["recommendations_text"] == "<ul><li>patch</li></ul>"


# ── slice #635: preview scaffold + report_preview module ────────────────────────


@pytest.mark.django_db
def test_preview_renders_readonly_sections_and_editable_defaults(acme, staff):
    from incidents.services.report_preview import build_report_preview

    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="public note", is_internal=False)
    tmpl = make_template(
        audience="internal",
        sections=["incident_details", "executive_summary", "recommendations"],
        intro_text="<p>intro</p>", recommendations_text="<p>rec default</p>",
    )
    data = build_report_preview(inc, tmpl, actor=staff)
    assert data["refused"] is False
    assert data["audience"] == "internal"
    by_kind = {s["kind"]: s for s in data["sections"]}
    # deterministic section is rendered read-only
    assert by_kind["incident_details"]["editable"] is False
    assert "<section" in by_kind["incident_details"]["html"]
    # editable sections carry no server html
    assert by_kind["executive_summary"]["editable"] is True
    assert "html" not in by_kind["recommendations"]
    # editable defaults pre-filled from the template; summary starts empty (on-demand)
    assert data["editable"]["intro_text"] == "<p>intro</p>"
    assert data["editable"]["recommendations_text"] == "<p>rec default</p>"
    assert data["editable"]["executive_summary"] == ""


@pytest.mark.django_db
def test_preview_customer_floor_excludes_internal_content(acme, staff):
    from incidents.services.report_preview import build_report_preview

    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="SECRET internal", is_internal=True)
    tmpl = make_template(audience="customer", sections=["timeline"])
    data = build_report_preview(inc, tmpl, actor=staff)
    blob = str(data)
    assert "SECRET internal" not in blob


@pytest.mark.django_db
def test_preview_customer_on_red_is_refused_with_no_body(acme, staff):
    from incidents.services.report_preview import build_report_preview

    inc = make_incident(acme, tlp="red")
    tmpl = make_template(audience="customer", sections=["incident_details"])
    data = build_report_preview(inc, tmpl, actor=staff)
    assert data["refused"] is True
    assert "sections" not in data
    assert data["reason"]


@pytest.mark.django_db
def test_preview_creates_no_artifacts(acme, staff):
    from incidents.models import IncidentEvent
    from incidents.services.report_preview import build_report_preview

    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["incident_details"])
    before_reports = Report.objects.count()
    before_events = IncidentEvent.objects.filter(incident=inc).count()
    build_report_preview(inc, tmpl, actor=staff)
    assert Report.objects.count() == before_reports
    assert IncidentEvent.objects.filter(incident=inc).count() == before_events


@pytest.mark.django_db
def test_preview_endpoint_staff_only(client, acme, staff, member):
    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["incident_details"])
    # org member forbidden
    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/preview/?template_id={tmpl.id}")
    assert resp.status_code in (401, 403)
    # staff ok
    client.force_login(staff)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/preview/?template_id={tmpl.id}")
    assert resp.status_code == 200
    assert resp.json()["refused"] is False


@pytest.mark.django_db
def test_preview_endpoint_requires_template_id(client, acme, staff):
    inc = make_incident(acme)
    client.force_login(staff)
    resp = client.get(f"/api/incidents/{inc.display_id}/reports/preview/")
    assert resp.status_code == 400


# ── slice #637: on-demand Executive Summary preview endpoint ─────────────────────


@pytest.mark.django_db
def test_summary_endpoint_returns_prose_and_persists_nothing(client, acme, staff):
    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["executive_summary"])
    client.force_login(staff)
    before = Report.objects.count()
    with patch(
        "incidents.llm.report_summary.generate_report_summary",
        return_value="<p>AI summary</p>",
    ):
        resp = client.post(
            f"/api/incidents/{inc.display_id}/reports/preview/summary/",
            {"template_id": tmpl.id}, content_type="application/json",
        )
    assert resp.status_code == 200, resp.content
    assert resp.json()["executive_summary"] == "<p>AI summary</p>"
    assert Report.objects.count() == before


@pytest.mark.django_db
def test_summary_endpoint_uses_audience_floored_grounding(client, acme, staff):
    inc = make_incident(acme, tlp="green")
    Comment.objects.create(incident=inc, body="SECRET internal", is_internal=True)
    tmpl = make_template(audience="customer", sections=["executive_summary"])
    client.force_login(staff)
    captured = {}

    def fake_summary(grounding):
        captured["grounding"] = grounding
        return "<p>ok</p>"

    with patch("incidents.llm.report_summary.generate_report_summary", side_effect=fake_summary):
        resp = client.post(
            f"/api/incidents/{inc.display_id}/reports/preview/summary/",
            {"template_id": tmpl.id}, content_type="application/json",
        )
    assert resp.status_code == 200
    bodies = [c["body"] for c in captured["grounding"]["comments"]]
    assert "SECRET internal" not in bodies


@pytest.mark.django_db
def test_summary_endpoint_customer_on_red_refused(client, acme, staff):
    inc = make_incident(acme, tlp="red")
    tmpl = make_template(audience="customer", sections=["executive_summary"])
    client.force_login(staff)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/reports/preview/summary/",
        {"template_id": tmpl.id}, content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_summary_endpoint_staff_only(client, acme, staff, member):
    inc = make_incident(acme)
    tmpl = make_template(audience="internal", sections=["executive_summary"])
    client.force_login(member)
    resp = client.post(
        f"/api/incidents/{inc.display_id}/reports/preview/summary/",
        {"template_id": tmpl.id}, content_type="application/json",
    )
    assert resp.status_code in (401, 403)
