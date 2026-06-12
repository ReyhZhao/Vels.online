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

# Raw Wazuh document fields that carry observables, by IOC-ish family. Mirrors the
# hunt lens field map (hunts.lenses._IOC_FIELDS) so the evidence we surface matches
# what the sweep searched on.
_IP_FIELDS = ["data.srcip", "data.dstip", "data.win.eventdata.destinationIp", "agent.ip"]
_DOMAIN_FIELDS = ["data.dns.question.name", "data.url", "data.win.eventdata.queryName"]
_HOST_FIELDS = ["agent.name", "predecoder.hostname", "data.hostname"]
_RULE_FIELDS = ["rule.description"]


def _dig(doc, dotted):
    """Return the value at a dotted path in a nested dict, or None."""
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _first(doc, fields):
    """First non-empty string value across the given dotted field paths."""
    for f in fields:
        val = _dig(doc, f)
        if isinstance(val, (str, int)) and str(val).strip():
            return str(val).strip()
    return None


def _collect(doc, fields):
    """All non-empty string values across the given dotted field paths."""
    out = []
    for f in fields:
        val = _dig(doc, f)
        if isinstance(val, (str, int)) and str(val).strip():
            out.append(str(val).strip())
    return out


def _build_promotion_description(hunt, findings):
    """A compact but information-rich incident description for a promoted hunt.

    Summarises the seed, the lens(es) that matched, and a per-finding evidence
    digest, plus an Observables block of harvested IPs/domains. The observable
    values are rendered as plain text so the existing IOC extractor (which scans
    title + description) lifts them into IOC rows with owned-asset exclusion.
    """
    seed = hunt.seed_url or (hunt.seed_text or "")
    lenses = sorted({f.lens for f in findings if f.lens})

    lines = [
        f"Promoted from Threat Hunt {hunt.id}.",
        f"Seed: {seed}" if seed else "Seed: (none)",
        f"Lens(es): {', '.join(lenses)}" if lenses else "",
        f"{len(findings)} matched Wazuh document(s) materialised as alerts.",
        "",
        "Evidence:",
    ]

    observables = []
    for finding in findings:
        doc = finding.raw_doc if isinstance(finding.raw_doc, dict) else {}
        host = _first(doc, _HOST_FIELDS) or "unknown host"
        rule = _first(doc, _RULE_FIELDS)
        ips = _collect(doc, _IP_FIELDS)
        domains = _collect(doc, _DOMAIN_FIELDS)
        observables.extend(ips)
        observables.extend(domains)

        bits = [f"host {host}"]
        if rule:
            bits.append(f'rule "{rule}"')
        if ips:
            bits.append("ip " + ", ".join(dict.fromkeys(ips)))
        if domains:
            bits.append("domain " + ", ".join(dict.fromkeys(domains)))
        summary = (finding.summary or "").strip()
        detail = f" — {summary}" if summary else ""
        lines.append(f"- {' · '.join(bits)}{detail}")

    deduped = list(dict.fromkeys(observables))
    if deduped:
        lines.extend(["", "Observables: " + ", ".join(deduped)])

    return "\n".join(line for line in lines if line is not None)


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
    from incidents.services.ioc_extraction import extract_and_save_iocs

    findings = list(
        hunt.findings.filter(organization=organization, materialised_incident__isnull=True)
    )
    if not findings:
        return None

    title = f"Threat hunt: {len(findings)} finding(s) in {organization.name}"
    description = _build_promotion_description(hunt, findings)

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
        # Agent-less Shared Infrastructure docs (agent.id="000") carry no agent.name —
        # fall back to "unknown" rather than erroring (ADR-0017).
        agent = source.get("agent") if isinstance(source, dict) else None
        agent_name = (agent or {}).get("name", "unknown") if isinstance(agent, dict) else "unknown"
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

    # Populate IOCs from the observables surfaced in the description (the extractor
    # scans title + description and excludes the org's owned assets). Safe to re-run:
    # IOC rows are unique per (incident, kind, value) and created with ignore_conflicts.
    extract_and_save_iocs(incident)

    return incident
