"""Incident Report generation service (PRD #618, ADR-0029).

``generate_report(incident, template, actor) -> Report`` is the one entry point:
render the ordered sections + free-text blocks through the Audience floor, convert
HTML → PDF (WeasyPrint), store the PDF, and freeze an immutable ``Report`` row with
denormalized snapshot fields. It records an ``IncidentEvent`` on success.

Leak-safety invariant: a ``customer`` Report ALWAYS renders through the customer
floor regardless of the (staff) actor who generates it, and a ``customer`` Report is
refused outright when the incident is TLP:RED.
"""
import html as _html
import logging
import uuid
from io import BytesIO

from security.storage import StorageClient

from ..models import Incident, Report, ReportTemplate
from ..llm.report_summary import generate_report_summary
from .events import record_event
from .identifiers import next_report_reference_id
from .report_grounding import build_report_grounding
from .report_sanitize import sanitize_report_richtext
from .report_sections import SECTION_TITLES, render_section

logger = logging.getLogger(__name__)

# SOC/platform branding used as letterhead (no per-org logo in v1).
SOC_BRAND = "Vels Online · Security Operations Centre"


class ReportGenerationError(Exception):
    """Raised when a Report cannot be generated (e.g. customer report on TLP:RED)."""


# User-facing refusal message. Kept as a module constant so the API layer can return
# it without reading the exception object — that keeps any exception/stack-trace detail
# from reaching the client (CWE-209) while preserving the same message for the user.
REPORT_REFUSAL_CUSTOMER_ON_RED = (
    "A customer report cannot be generated for a TLP:RED incident."
)


def _esc(value) -> str:
    return _html.escape(str(value if value is not None else ""))


def _render_section_html(section: dict) -> str:
    kind = section["kind"]
    title = section["title"]
    ctx = section["context"]
    body = ""

    if kind == "incident_details":
        rows = "".join(
            f"<tr><th>{_esc(label)}</th><td>{_esc(val)}</td></tr>"
            for label, val in ctx.get("rows", [])
        )
        body = f"<table class='details'>{rows}</table>"
        if ctx.get("description"):
            body += f"<p class='description'>{_esc(ctx['description'])}</p>"

    elif kind == "executive_summary":
        # Rich-text: the prose is sanitized (allowlist) and emitted as markup, not
        # escaped — the sanitizer is the security boundary (PRD #632).
        summary = sanitize_report_richtext(ctx.get("summary", ""))
        body = (
            f"<div class='richtext'>{summary}</div>" if summary
            else "<p class='muted'>No summary available.</p>"
        )

    elif kind == "timeline":
        entries = ctx.get("entries", [])
        if entries:
            items = "".join(
                f"<li><span class='ts'>{_esc(e['created_at'])}</span> "
                f"<span class='ev'>{_esc(e['label'])}</span>"
                + (f" — {_esc(e['actor'])}" if e.get("actor") else "")
                + "</li>"
                for e in entries
            )
            body = f"<ul class='timeline'>{items}</ul>"
        else:
            body = "<p class='muted'>No timeline entries to display.</p>"

    elif kind == "iocs":
        if ctx.get("suppressed"):
            body = (
                "<p class='muted'>Indicators are withheld for this report's "
                "handling restrictions (PAP).</p>"
            )
        elif ctx.get("indicators"):
            items = "".join(
                f"<li><span class='ioc-kind'>{_esc(i['kind'])}</span>: "
                f"<code>{_esc(i['value'])}</code></li>"
                for i in ctx["indicators"]
            )
            body = f"<ul class='iocs'>{items}</ul>"
        else:
            body = "<p class='muted'>No indicators recorded.</p>"

    elif kind == "actions_taken":
        actions = ctx.get("actions", [])
        if actions:
            items = "".join(
                f"<li>{_esc(a['title'])} "
                f"<span class='task-type'>({_esc(a['type_label'])})</span></li>"
                for a in actions
            )
            body = f"<ul class='actions'>{items}</ul>"
        else:
            body = "<p class='muted'>No completed actions to report.</p>"

    elif kind == "asset_impact":
        assets = ctx.get("assets", [])
        if assets:
            rows = "".join(
                f"<tr><td>{_esc(a['name'])}</td><td>{_esc(a['role'])}</td></tr>"
                for a in assets
            )
            body = (
                "<table class='assets'><tr><th>Asset</th><th>Role</th></tr>"
                f"{rows}</table>"
            )
        else:
            body = "<p class='muted'>No affected assets recorded.</p>"

    elif kind == "recommendations":
        text = sanitize_report_richtext(ctx.get("text", ""))
        body = (
            f"<div class='richtext'>{text}</div>" if text
            else "<p class='muted'>No recommendations provided.</p>"
        )

    return f"<section class='report-section'><h2>{_esc(title)}</h2>{body}</section>"


_STYLE = """
  @page { size: A4; margin: 2cm; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 11pt; }
  .letterhead { border-bottom: 3px solid #2b4a8b; padding-bottom: 8px; margin-bottom: 4px; }
  .letterhead .brand { font-size: 14pt; font-weight: bold; color: #2b4a8b; }
  .prepared-for { color: #555; margin: 2px 0 16px; }
  .report-ref { color: #888; font-size: 9pt; }
  h1 { font-size: 18pt; margin: 8px 0 4px; }
  h2 { font-size: 13pt; color: #2b4a8b; border-bottom: 1px solid #ddd; padding-bottom: 3px; margin-top: 20px; }
  table.details th { text-align: left; width: 140px; color: #555; vertical-align: top; padding: 2px 8px 2px 0; }
  table.details td { padding: 2px 0; }
  table.assets { border-collapse: collapse; width: 100%; }
  table.assets th, table.assets td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; }
  ul.timeline, ul.iocs, ul.actions { padding-left: 18px; }
  .ts { color: #888; font-size: 9pt; }
  .muted { color: #999; font-style: italic; }
  .description { margin-top: 10px; white-space: pre-wrap; }
  .intro, .outro { margin: 12px 0; }
  /* Rich-text blocks (intro/outro/recommendations/executive summary). Keep this in
     sync with the frontend preview stylesheet so the live preview matches the PDF. */
  .richtext p { margin: 6px 0; }
  .richtext ul, .richtext ol { padding-left: 22px; margin: 6px 0; }
  .richtext u { text-decoration: underline; }
  .richtext .indent-1 { margin-left: 2em; }
  .richtext .indent-2 { margin-left: 4em; }
  .richtext .indent-3 { margin-left: 6em; }
"""


def render_report_html(incident, template, grounding, sections) -> str:
    """Compose the ordered sections + free-text blocks into a single HTML document.

    Pure given its inputs.
    """
    org_name = grounding["incident"]["organization"]
    sections_html = "".join(_render_section_html(s) for s in sections)
    # Intro/outro are rich-text: prefer a per-Report override frozen into the grounding
    # (PRD #632), falling back to the template default. Either way they are sanitized
    # (allowlist) and emitted as markup, never escaped.
    intro_src = grounding.get("intro_text", template.intro_text)
    outro_src = grounding.get("outro_text", template.outro_text)
    intro_html = sanitize_report_richtext(intro_src)
    outro_html = sanitize_report_richtext(outro_src)
    intro = f"<div class='intro richtext'>{intro_html}</div>" if intro_html else ""
    outro = f"<div class='outro richtext'>{outro_html}</div>" if outro_html else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <div class="letterhead"><span class="brand">{_esc(SOC_BRAND)}</span></div>
  <div class="prepared-for">Prepared for: {_esc(org_name)}</div>
  <h1>{_esc(incident.title)}</h1>
  <div class="report-ref">Incident {_esc(incident.display_id)} ·
    {_esc(dict(ReportTemplate.AUDIENCE_CHOICES).get(template.audience, template.audience))} report</div>
  {intro}
  {sections_html}
  {outro}
</body></html>"""


def render_report_pdf(html: str) -> bytes:
    """Render an HTML document to PDF bytes via WeasyPrint."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


# The free-text blocks an analyst may override per-Report in the Preview (PRD #632).
OVERRIDE_KEYS = ("intro_text", "outro_text", "recommendations_text", "executive_summary")


def _effective_richtext(overrides, key, default):
    """A per-Report override (sanitized) when the analyst supplied one, else the default.

    "Supplied" means the key is present with a string value — an empty string is a
    deliberate clear, not "fall back to the template".
    """
    if overrides and isinstance(overrides.get(key), str):
        return sanitize_report_richtext(overrides[key])
    return default


def generate_report(incident, template, actor, overrides=None) -> Report:
    """Render, store, and freeze an immutable Report of ``incident`` from ``template``.

    Enforces the leak-safety rules: a ``customer`` Report always renders through the
    customer Audience floor (independent of ``actor``), and a ``customer`` Report is
    refused on a TLP:RED incident.

    ``overrides`` (PRD #632) may carry per-Report free-text for any of
    ``OVERRIDE_KEYS``. Each is sanitized and frozen into THIS Report only — the source
    ``template`` is never mutated. A supplied ``executive_summary`` is used verbatim and
    the LLM call is skipped (the analyst already vetted it in the Preview).
    """
    audience = template.audience
    overrides = overrides or {}

    if audience == ReportTemplate.AUDIENCE_CUSTOMER and incident.tlp == Incident.TLP_RED:
        raise ReportGenerationError(REPORT_REFUSAL_CUSTOMER_ON_RED)

    # The floor is keyed on the template's Audience, NOT on the (staff) actor — a
    # customer report renders the customer perspective no matter who generates it.
    grounding = build_report_grounding(incident, audience)

    # Freeze the effective (override-or-template, sanitized) free-text into the grounding
    # so the renderers read it; never written back to the template.
    intro_text = _effective_richtext(overrides, "intro_text", template.intro_text)
    outro_text = _effective_richtext(overrides, "outro_text", template.outro_text)
    recommendations_text = _effective_richtext(
        overrides, "recommendations_text", template.recommendations_text
    )
    grounding["intro_text"] = intro_text
    grounding["outro_text"] = outro_text
    grounding["recommendations_text"] = recommendations_text

    section_kinds = list(template.sections or [])

    executive_summary = ""
    if "executive_summary" in section_kinds:
        if isinstance(overrides.get("executive_summary"), str):
            # Analyst-vetted prose from the Preview — freeze verbatim, skip the LLM.
            executive_summary = sanitize_report_richtext(overrides["executive_summary"])
        else:
            executive_summary = sanitize_report_richtext(generate_report_summary(grounding))
        # Freeze the prose into the grounding so the section renderer reads it and it
        # is captured in the immutable snapshot — never re-run on later views.
        grounding["executive_summary"] = executive_summary

    rendered = []
    for kind in section_kinds:
        rendered.append({
            "kind": kind,
            "title": SECTION_TITLES.get(kind, kind),
            "context": render_section(kind, incident, grounding, template),
        })

    html = render_report_html(incident, template, grounding, rendered)
    pdf_bytes = render_report_pdf(html)

    reference_id = next_report_reference_id()
    key = f"incidents/{incident.id}/reports/{uuid.uuid4()}-{reference_id}.pdf"
    StorageClient().upload_file(BytesIO(pdf_bytes), key)

    report = Report.objects.create(
        incident=incident,
        template=template,
        reference_id=reference_id,
        template_name=template.name,
        audience=audience,
        tlp=incident.tlp,
        incident_state=incident.state,
        executive_summary=executive_summary,
        content={
            "intro_text": intro_text,
            "outro_text": outro_text,
            "recommendations_text": recommendations_text,
            "sections": rendered,
        },
        s3_key=key,
        size_bytes=len(pdf_bytes),
        generated_by=actor,
    )
    record_event(
        incident, "report_generated", actor=actor,
        payload={
            "report_id": report.id,
            "reference_id": reference_id,
            "template_name": template.name,
            "audience": audience,
        },
    )
    return report


def issue_report_download_url(report, expiry_seconds=300):
    return StorageClient().generate_presigned_url(report.s3_key, expiry_seconds=expiry_seconds)
