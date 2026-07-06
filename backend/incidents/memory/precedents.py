"""Precedent retrieval for the Triage Classify phase (ADR-0030, slice #660).

A **Precedent** is a single *resolved* Incident from the **same Organization**, retrieved
as a worked example so Classify can reason "this looks like INC-1234, which was closed as
a false positive because X". Strictly per-tenant (ADR-0031): precedents are only ever
drawn from the incident's own organisation — raw cases never cross tenants. No vector
store: candidates are matched by shared Entities/IOCs (issue #657 tracks semantic
retrieval as a v2 axis).
"""
import logging

from django.db.models import Q

logger = logging.getLogger(__name__)

PRECEDENT_LIMIT = 5
_RESOLUTION_COMMENTS = 3
_COMMENT_SNIPPET_MAX = 240


def _matching_keys(incident):
    """The Entity/IOC values used to find similar resolved incidents."""
    ioc_values = {v for v in incident.iocs.values_list("value", flat=True) if v}
    asset_names, asset_ips = set(), set()
    for ia in incident.incident_assets.select_related("asset").all():
        if ia.asset.agent_name:
            asset_names.add(ia.asset.agent_name)
        if ia.asset.ip_address:
            asset_ips.add(str(ia.asset.ip_address))
    return ioc_values, asset_names, asset_ips


def was_corrected(incident) -> bool:
    """Whether a human overturned the agent's Classify call on this incident.

    Slice #660 has no ClassificationCorrection store yet, so this is always False;
    slice #665 wires the real signal. Kept here so the Precedent shape is stable.
    """
    try:
        from incidents.models import ClassificationCorrection
    except ImportError:
        return False
    return ClassificationCorrection.objects.filter(incident=incident).exists()


def build_precedents(incident, *, limit=PRECEDENT_LIMIT):
    """Return resolved same-org Incidents similar to `incident`, enriched for Classify.

    Matched by a shared IOC value or a shared Asset (agent_name / ip). Each precedent
    carries its `closure_reason`, final (human-ratified) subject/severity, and recent
    resolution comments. Returns ``[]`` when the incident carries no matchable keys or
    nothing similar has been resolved.
    """
    from incidents.models import Comment, Incident

    ioc_values, asset_names, asset_ips = _matching_keys(incident)
    if not (ioc_values or asset_names or asset_ips):
        return []

    match = Q()
    if ioc_values:
        match |= Q(iocs__value__in=ioc_values)
    if asset_names:
        match |= Q(incident_assets__asset__agent_name__in=asset_names)
    if asset_ips:
        match |= Q(incident_assets__asset__ip_address__in=asset_ips)

    # Isolation invariant (ADR-0031): hard-filter on the incident's own organisation.
    candidates = (
        Incident.objects
        .filter(organization_id=incident.organization_id, state=Incident.STATE_CLOSED)
        .filter(closure_reason__isnull=False)
        .exclude(pk=incident.pk)
        .filter(match)
        .select_related("subject")
        .distinct()
        .order_by("-updated_at")[:limit]
    )

    precedents = []
    for inc in candidates:
        comments = list(
            Comment.objects.filter(incident=inc)
            .exclude(body="")
            .order_by("-created_at")
            .values_list("body", flat=True)[:_RESOLUTION_COMMENTS]
        )
        precedents.append({
            "display_id": inc.display_id,
            "title": inc.title,
            "closure_reason": inc.closure_reason,
            "final_subject": inc.subject.name if inc.subject else None,
            "final_severity": inc.severity,
            "resolution_comments": [_snippet(c) for c in reversed(comments)],
            "corrected_from_agent": was_corrected(inc),
        })
    return precedents


def _snippet(body: str) -> str:
    text = " ".join((body or "").split())
    return text[:_COMMENT_SNIPPET_MAX] + "…" if len(text) > _COMMENT_SNIPPET_MAX else text


def build_precedent_context(precedents) -> str:
    """Render precedents into a prompt block folded into the Classify extra_context."""
    if not precedents:
        return ""
    lines = [
        "Precedents — similar resolved incidents in THIS organisation. Use them to inform "
        "the false-positive call, disposition confidence, severity, and subject:"
    ]
    for p in precedents:
        subj = p["final_subject"] or "unclassified"
        corrected = " [an analyst reclassified this from the agent's original call]" if p.get("corrected_from_agent") else ""
        lines.append(
            f"  - {p['display_id']}: {p['title']} → closed as {p['closure_reason']}; "
            f"final subject={subj}, severity={p['final_severity']}{corrected}"
        )
        for c in p["resolution_comments"]:
            if c:
                lines.append(f"      · {c}")
    return "\n".join(lines)
