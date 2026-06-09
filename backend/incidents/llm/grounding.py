from incidents.services.transitions import ALLOWED_TRANSITIONS
from incidents.llm.base import ASSISTANT_FIELD_ALLOWLIST


def _ioc_annotation(ioc):
    vt = ioc.enrichment_data.get("virustotal", {}) if ioc.enrichment_data else {}
    if vt.get("status") == "done":
        return f"{ioc.value} (VirusTotal: {vt['malicious']}/{vt['total']} engines malicious)"
    return ioc.value


def build_incident_grounding(incident) -> dict:
    """Return a grounding dict for the incident assistant endpoint.

    Recomputed server-side every turn; never read from the client.
    """
    from incidents.models import TaskTemplate

    assets = [
        {
            "name": ia.asset.name,
            "kind": ia.asset.kind,
            "agent_name": ia.asset.agent_name,
            "ip_address": str(ia.asset.ip_address) if ia.asset.ip_address else None,
        }
        for ia in incident.incident_assets.select_related("asset").all()
    ]

    iocs = [
        {"kind": ioc.kind, "value": _ioc_annotation(ioc)}
        for ioc in incident.iocs.all()
    ]

    from alerts.models import Alert
    linked_alerts = list(
        Alert.objects.filter(incident=incident).values(
            "display_id", "title", "severity", "source_kind", "created_at"
        ).order_by("-created_at")[:20]
    )
    for a in linked_alerts:
        if a.get("created_at"):
            a["created_at"] = a["created_at"].isoformat()

    tasks = [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "task_type": t.task_type,
            "state": t.state,
            "assignee": t.assignee.username if t.assignee else None,
        }
        for t in incident.tasks.select_related("assignee").all()
    ]

    applied_templates = sorted(
        {
            app.template.name
            for app in incident.template_applications.select_related("template").all()
        }
    )

    available_templates = []
    if incident.subject_id:
        for tmpl in TaskTemplate.objects.filter(subject=incident.subject).prefetch_related("items"):
            available_templates.append({
                "id": tmpl.id,
                "name": tmpl.name,
                "description": tmpl.description,
                "item_count": tmpl.items.count(),
            })

    allowed_transitions = sorted(ALLOWED_TRANSITIONS.get(incident.state, set()))

    from contacts.models import IncidentContact
    contacts = [
        {"id": r.contact_id, "name": r.contact.name}
        for r in IncidentContact.objects.filter(incident=incident).select_related("contact")
    ]

    return {
        "incident": {
            "display_id": incident.display_id,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "tlp": incident.tlp,
            "pap": incident.pap,
            "state": incident.state,
            "subject": incident.subject.name if incident.subject else None,
            "subject_slug": incident.subject.slug if incident.subject else None,
            "assignee": incident.assignee.username if incident.assignee else None,
            "assignee_id": incident.assignee_id,
            "source_kind": incident.source_kind,
            "source_ref": incident.source_ref,
            "created_at": incident.created_at.isoformat(),
            "closure_reason": incident.closure_reason,
        },
        "assets": assets,
        "iocs": iocs,
        "linked_alerts": linked_alerts,
        "tasks": tasks,
        "applied_templates": applied_templates,
        "available_templates": available_templates,
        "allowed_transitions": allowed_transitions,
        "field_allowlist": sorted(ASSISTANT_FIELD_ALLOWLIST),
        "contacts": contacts,
    }
