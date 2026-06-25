"""Tests for the Incident Assistant's propose_generate_report tool (PRD #625).

Generating an outward-facing Report is a propose-and-confirm action (ADR-0012/0029):
the assistant proposes (selecting a template), the analyst confirms, and confirmation
runs the same generate_report service. The assistant never generates unattended.
"""
from unittest.mock import MagicMock, patch

import pytest

from incidents.llm.action_authority import is_auto_executable, is_proposable
from incidents.llm.gemini import _parse_assistant_result
from incidents.llm.grounding import build_incident_grounding
from incidents.models import Incident, Report, ReportTemplate
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="sam", password="pass", is_staff=True)


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(
        organization=acme, title="Phishing", display_id="INC-2026-0500",
        tlp="green", pap="green", state="in_progress",
    )


@pytest.fixture
def template(db):
    return ReportTemplate.objects.create(
        organization=None, name="Customer Brief", audience="customer",
        sections=["incident_details"],
    )


def test_propose_generate_report_is_proposable_not_auto():
    assert is_proposable("propose_generate_report")
    assert not is_auto_executable("propose_generate_report")


@pytest.mark.django_db
def test_grounding_lists_available_report_templates(incident, template):
    g = build_incident_grounding(incident)
    ids = [t["id"] for t in g["available_report_templates"]]
    assert template.id in ids


@pytest.mark.django_db
def test_assistant_returns_proposal_not_generation(incident, template):
    """The tool returns a proposal; it must NOT generate a Report."""
    g = build_incident_grounding(incident)
    data = {
        "assistant_reply": "I can generate a customer report.",
        "proposed_actions": [
            {"type": "propose_generate_report", "template_id": template.id,
             "label": "Generate customer report"},
        ],
    }
    result = _parse_assistant_result(data, g)
    assert len(result.proposed_actions) == 1
    act = result.proposed_actions[0]
    assert act.type == "propose_generate_report"
    assert act.payload["template_id"] == template.id
    assert act.payload["audience"] == "customer"
    # Proposing must never have generated anything.
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_assistant_proposal_rejects_unknown_template(incident, template):
    g = build_incident_grounding(incident)
    data = {
        "assistant_reply": "x",
        "proposed_actions": [
            {"type": "propose_generate_report", "template_id": 999999, "label": "bad"},
        ],
    }
    result = _parse_assistant_result(data, g)
    assert result.proposed_actions == []
    assert result.warnings


@pytest.mark.django_db
def test_confirming_proposal_generates_report(incident, template, staff):
    """Confirmation runs the generation service and produces a Report."""
    from incidents.services.reports import generate_report

    with patch("incidents.services.reports.render_report_pdf", return_value=b"%PDF-1.4 x"), \
         patch("incidents.services.reports.StorageClient") as Storage:
        Storage.return_value.upload_file = MagicMock()
        report = generate_report(incident, template, actor=staff)

    assert Report.objects.count() == 1
    assert report.template_name == "Customer Brief"
    assert report.audience == "customer"
