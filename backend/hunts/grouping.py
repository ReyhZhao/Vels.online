"""Group Hunt Findings by org and materialise a per-org Incident (ADR-0015, deep module).

A Hunt never auto-creates incidents. Its Findings are grouped by affected org and each
group is a propose-and-confirm Incident: on confirm, the matched raw Wazuh docs are
materialised as Alerts (source_kind=threat_hunt, born-linked + suppressed like the
Scheduled Search Rule bridge) and linked to a fresh Incident *in that org's scope*. One
seed touching three tenants yields up to three separate incidents — never a cross-tenant
joined one.
"""
import logging
from collections import OrderedDict

from django.db import transaction

logger = logging.getLogger(__name__)


def group_findings_by_org(hunt):
    """Return an OrderedDict {Organization: [HuntFinding, ...]} for unmaterialised findings."""
    groups = OrderedDict()
    qs = (
        hunt.findings.filter(materialised_incident__isnull=True)
        .select_related("organization")
        .order_by("organization_id", "created_at")
    )
    for finding in qs:
        groups.setdefault(finding.organization, []).append(finding)
    return groups


def proposed_incidents(hunt):
    """Summarise the propose-and-confirm incidents a Hunt currently offers, per org."""
    out = []
    for org, findings in group_findings_by_org(hunt).items():
        out.append({
            "organization_id": org.id,
            "organization_name": org.name,
            "finding_count": len(findings),
            "finding_ids": [f.id for f in findings],
        })
    return out


@transaction.atomic
def materialise_findings_for_org(hunt, organization, user=None):
    """Confirm a Hunt's findings for one org → a new Incident with materialised Alerts.

    Idempotent per finding (a finding already linked to an incident is skipped).
    Returns the created Incident, or None when there were no unmaterialised findings.
    """
    from alerts.models import Alert
    from alerts.services.identifiers import next_alert_display_id
    from incidents.models import Incident
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id

    findings = list(
        hunt.findings.filter(organization=organization, materialised_incident__isnull=True)
    )
    if not findings:
        return None

    title = f"Threat hunt: {len(findings)} finding(s) in {organization.name}"
    seed = hunt.seed_url or (hunt.seed_text[:200] if hunt.seed_text else "")
    description = (
        f"Promoted from Threat Hunt {hunt.id}.\n"
        f"Seed: {seed}\n"
        f"{len(findings)} matched Wazuh document(s) materialised as alerts."
    )

    ser = IncidentCreateSerializer(data={
        "title": title[:255],
        "severity": "medium",
        "source_kind": Incident.SOURCE_THREAT_HUNT,
        "description": description,
        "tlp": "amber",
        "pap": "amber",
    })
    ser.is_valid(raise_exception=True)
    incident = ser.save(
        organization=organization, display_id=next_display_id(), created_by=user,
    )
    record_event(
        incident, "incident_created", actor=user,
        payload={"source": "threat_hunt", "hunt_id": str(hunt.id)},
    )

    for finding in findings:
        source = finding.raw_doc or {}
        agent_name = source.get("agent", {}).get("name", "unknown") if isinstance(source, dict) else "unknown"
        alert = Alert.objects.create(
            organization=organization,
            display_id=next_alert_display_id(),
            source_kind="threat_hunt",
            source_ref=source if isinstance(source, dict) else {},
            title=(finding.summary or f"Threat hunt finding on {agent_name}")[:255],
            severity="medium",
            state="imported",
            description=f"Materialised from Threat Hunt {hunt.id} (lens: {finding.lens}).",
            incident=incident,
        )
        finding.materialised_incident = incident
        finding.save(update_fields=["materialised_incident"])
        record_event(
            incident, "alert_linked", actor=user,
            payload={"alert_display_id": alert.display_id, "source": "threat_hunt"},
        )

    return incident
