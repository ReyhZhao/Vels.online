"""The Report Section catalog (PRD #618, ADR-0029).

A server-side registry mapping a section *kind* to a renderer
``render(incident, grounding, template) -> section_context``. Every renderer
draws ONLY from the audience-filtered ``grounding`` (see
``incidents.services.report_grounding.build_report_grounding``) or from
template-authored free text, so the Audience floor is enforced structurally.

Adding a section is a code change here — never a template-author action. The
template only references the kinds this catalog registers, in an order it chooses.

Section-specific disclosure rules beyond the TLP floor:

* IOCs respect a PAP *ceiling* — indicators render only at PAP:WHITE/GREEN and are
  suppressed entirely at PAP:AMBER/RED (the one place indicators leave the platform).
* Asset Impact renders Asset names/roles only and OMITS all Exposure specifics — a
  customer report must not double as an exposure map of the customer's own hosts.
"""
from incidents.models import Incident

# Human-readable labels for the catalog kinds (used by the authoring UI + headings).
SECTION_TITLES = {
    "executive_summary": "Executive Summary",
    "incident_details": "Incident Details",
    "timeline": "Timeline",
    "iocs": "Indicators of Compromise",
    "actions_taken": "Actions Taken",
    "asset_impact": "Asset Impact",
    "recommendations": "Recommendations",
}

_SEVERITY_LABELS = dict(Incident.SEVERITY_CHOICES)
_STATE_LABELS = dict(Incident.STATE_CHOICES)
_TLP_LABELS = dict(Incident.TLP_CHOICES)
_PAP_AMBER_RED = (Incident.PAP_AMBER, Incident.PAP_RED)


def _render_incident_details(incident, grounding, template):
    inc = grounding["incident"]
    return {
        "rows": [
            ("Reference", inc["display_id"]),
            ("Title", inc["title"]),
            ("Severity", _SEVERITY_LABELS.get(inc["severity"], inc["severity"])),
            ("Subject", inc["subject"] or "—"),
            ("State", _STATE_LABELS.get(inc["state"], inc["state"])),
            ("TLP", _TLP_LABELS.get(inc["tlp"], inc["tlp"])),
            ("Opened", inc["created_at"]),
        ],
        "description": inc["description"],
    }


def _render_timeline(incident, grounding, template):
    # Events are already filtered through the Audience floor in the grounding.
    entries = [
        {
            "kind": e["kind"],
            "label": e["kind"].replace("_", " ").title(),
            "actor": e["actor"],
            "created_at": e["created_at"],
        }
        for e in grounding["events"]
    ]
    return {"entries": entries}


def _render_iocs(incident, grounding, template):
    # PAP ceiling: indicators only leave the platform at PAP:WHITE/GREEN.
    if incident.pap in _PAP_AMBER_RED:
        return {"suppressed": True, "reason": "pap_ceiling", "indicators": []}
    return {
        "suppressed": False,
        "indicators": [
            {"kind": i["kind"], "value": i["value"]} for i in grounding["iocs"]
        ],
    }


def _render_actions_taken(incident, grounding, template):
    # Completed tasks only, title + type — never the tasks' internal comments /
    # AI findings (those are is_internal and must not leak into a customer Report).
    actions = [
        {
            "title": t["title"],
            "task_type": t["task_type"],
            "type_label": t["task_type"].replace("_", " ").title(),
            "completed_at": t["closed_at"],
        }
        for t in grounding["tasks"]
    ]
    return {"actions": actions}


def _render_asset_impact(incident, grounding, template):
    # Names and roles only — NO Exposure specifics (NAT protocol/port, route
    # fqdn/backend, protection trait). The grounding deliberately carries no exposure.
    assets = [
        {"name": a["name"], "role": a["role"] or "—", "kind": a["kind"]}
        for a in grounding["assets"]
    ]
    return {"assets": assets}


def _render_recommendations(incident, grounding, template):
    # Prefer a per-Report override frozen into the grounding (PRD #632); fall back to
    # the template default. The renderer in reports.py sanitizes the text.
    override = grounding.get("recommendations_text")
    text = override if override is not None else template.recommendations_text
    return {"text": (text or "").strip()}


def _render_executive_summary(incident, grounding, template):
    # The prose is generated at render time and injected into the grounding by the
    # generation service (so it is frozen into the snapshot, never re-run on view).
    return {"summary": grounding.get("executive_summary", "")}


SECTION_CATALOG = {
    "executive_summary": _render_executive_summary,
    "incident_details": _render_incident_details,
    "timeline": _render_timeline,
    "iocs": _render_iocs,
    "actions_taken": _render_actions_taken,
    "asset_impact": _render_asset_impact,
    "recommendations": _render_recommendations,
}


def catalog_kinds():
    """The section kinds a template author may choose from, in catalog order."""
    return list(SECTION_CATALOG.keys())


def render_section(kind, incident, grounding, template):
    """Render one section kind to its context dict. Unknown kinds render empty."""
    renderer = SECTION_CATALOG.get(kind)
    if renderer is None:
        return {}
    return renderer(incident, grounding, template)
