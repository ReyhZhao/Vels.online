"""Non-persisting Report Preview scaffold (PRD #632, ADR-0029 amendment).

``build_report_preview(incident, template, actor) -> dict`` returns what a Report from
``template`` would look like for ``incident`` right now — the deterministic sections
rendered read-only through the SAME Audience floor as generation, plus the editable
free-text defaults — WITHOUT persisting anything (no Report row, no PDF, no IncidentEvent).

It is a staff authoring aid, never an artifact. The leak-safety invariant is identical to
generation: a ``customer`` preview renders the customer floor regardless of the (staff)
actor, and a ``customer`` preview on a TLP:RED incident renders NO body at all — the same
early-out as ``generate_report`` — so a customer body is never produced for a RED incident
even in preview.
"""
from ..models import Incident, ReportTemplate
from .report_grounding import build_report_grounding
from .report_sections import SECTION_TITLES, render_section
from .reports import REPORT_REFUSAL_CUSTOMER_ON_RED, _render_section_html

# Section kinds whose body is an editable free-text block, not machine-derived content.
# The frontend renders an editor for these instead of read-only HTML.
EDITABLE_SECTION_KINDS = {"executive_summary", "recommendations"}


def build_report_preview(incident, template, actor) -> dict:
    """Return the non-persisting preview scaffold for ``incident`` from ``template``.

    Shape::

        {
          "refused": bool,
          "reason": str,            # only when refused
          "audience": "customer" | "internal",
          "sections": [             # ordered as the template specifies
            {"kind", "title", "editable": False, "html": "<section>…"},   # read-only
            {"kind", "title", "editable": True},                          # editor block
          ],
          "editable": {"intro_text", "outro_text", "recommendations_text",
                       "executive_summary"},   # pre-fill defaults
        }
    """
    audience = template.audience

    # Same early-out as generate_report — never render a customer body at TLP:RED.
    if audience == ReportTemplate.AUDIENCE_CUSTOMER and incident.tlp == Incident.TLP_RED:
        return {
            "refused": True,
            "reason": REPORT_REFUSAL_CUSTOMER_ON_RED,
            "audience": audience,
        }

    # The floor is keyed on the template's Audience, not on the (staff) actor.
    grounding = build_report_grounding(incident, audience)

    sections = []
    for kind in (template.sections or []):
        title = SECTION_TITLES.get(kind, kind)
        if kind in EDITABLE_SECTION_KINDS:
            # Editable: the frontend renders the editor + live rich-text, so no server
            # render here (the Executive Summary is generated on demand via its endpoint).
            sections.append({"kind": kind, "title": title, "editable": True})
        else:
            ctx = render_section(kind, incident, grounding, template)
            html = _render_section_html({"kind": kind, "title": title, "context": ctx})
            sections.append({"kind": kind, "title": title, "editable": False, "html": html})

    return {
        "refused": False,
        "audience": audience,
        "sections": sections,
        "editable": {
            "intro_text": template.intro_text,
            "outro_text": template.outro_text,
            "recommendations_text": template.recommendations_text,
            "executive_summary": "",  # generated on demand in the preview
        },
    }
