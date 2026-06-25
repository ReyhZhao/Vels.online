"""Audience-filtered grounding for incident Reports (PRD #618 / #620, ADR-0029).

This is the leak-safety spine. ``build_report_grounding(incident, audience)``
builds the only data a Report — and the executive-summary LLM call — may use,
applying the same visibility floor an Organization member would get for a
``customer`` Audience, regardless of which (staff) member generates the Report.

It is DELIBERATELY SEPARATE from ``incidents.llm.grounding.build_incident_grounding``,
which has NO visibility floor and must never feed a customer Report. The two must be
kept in sync as the floor evolves, but they are not interchangeable.

The floor mirrors ``incidents/services/visibility.py`` semantics
(``filter_comments_for_user`` / ``filter_events_for_user``) but from the report's
perspective — there is no live request user, only an Audience:

* ``internal`` — full fidelity (everything a staff member would see).
* ``customer`` — what an org member sees:
    - TLP:WHITE/GREEN  → non-internal comments/events only
    - TLP:AMBER/RED    → no comments, no events at all
"""
from incidents.models import Incident, ReportTemplate, Task


def _is_customer(audience) -> bool:
    return audience == ReportTemplate.AUDIENCE_CUSTOMER


def _customer_sees_discussion(incident) -> bool:
    """An org member sees comments/events only at TLP:WHITE/GREEN (visibility.py)."""
    return incident.tlp not in (Incident.TLP_AMBER, Incident.TLP_RED)


def filter_comments_for_audience(qs, incident, audience):
    """Mirror ``filter_comments_for_user`` from the report's perspective."""
    if not _is_customer(audience):
        return qs
    if not _customer_sees_discussion(incident):
        return qs.none()
    return qs.filter(is_internal=False)


def filter_events_for_audience(qs, incident, audience):
    """Mirror ``filter_events_for_user`` from the report's perspective."""
    if not _is_customer(audience):
        return qs
    if not _customer_sees_discussion(incident):
        return qs.none()
    from django.db.models import Q

    # Keep events that either lack the is_internal key or have it set to False —
    # exactly as filter_events_for_user does for org members.
    return qs.filter(
        Q(payload__is_internal=False) | ~Q(payload__has_key="is_internal")
    )


def build_report_grounding(incident, audience) -> dict:
    """Return the audience-filtered grounding for a Report of ``incident``.

    Every collection here has passed through the Audience floor, so a ``customer``
    Report (and its executive summary) can only ever touch customer-visible content.
    """
    comments_qs = filter_comments_for_audience(
        incident.comments.filter(deleted_at__isnull=True).select_related("author"),
        incident, audience,
    ).order_by("created_at")
    events_qs = filter_events_for_audience(
        incident.events.select_related("actor"), incident, audience
    ).order_by("created_at")

    comments = [
        {
            "id": c.id,
            "body": c.body,
            "author": c.author.username if c.author else None,
            "kind": c.kind,
            "is_internal": c.is_internal,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments_qs
    ]
    events = [
        {
            "id": e.id,
            "kind": e.kind,
            "actor": e.actor.username if e.actor else None,
            "payload": e.payload or {},
            "created_at": e.created_at.isoformat(),
        }
        for e in events_qs
    ]

    iocs = [
        {"kind": ioc.kind, "value": ioc.value}
        for ioc in incident.iocs.all()
    ]

    completed_tasks = [
        {
            "id": t.id,
            "title": t.title,
            "task_type": t.task_type,
            "state": t.state,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in incident.tasks.filter(state=Task.STATE_DONE).order_by("display_order", "created_at")
    ]

    assets = [
        {"name": ia.asset.name, "role": ia.asset.role, "kind": ia.asset.kind}
        for ia in incident.incident_assets.select_related("asset").all()
    ]

    return {
        "audience": audience,
        "incident": {
            "display_id": incident.display_id,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "tlp": incident.tlp,
            "pap": incident.pap,
            "state": incident.state,
            "subject": incident.subject.name if incident.subject else None,
            "organization": incident.organization.name,
            "created_at": incident.created_at.isoformat(),
            "closure_reason": incident.closure_reason,
        },
        "comments": comments,
        "events": events,
        "iocs": iocs,
        "tasks": completed_tasks,
        "assets": assets,
    }
