"""End-to-end evaluator for Scheduled Search Rules."""
import json
import logging

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from correlations.services.search_compiler import _ALERTS_INDEX, compile_query

logger = logging.getLogger(__name__)


def _compose_description(rule, alerts) -> str:
    lines = [
        f"Scheduled search rule **{rule.name}** fired.",
        f"Description: {rule.description}" if rule.description else "",
        "",
        f"## Matched documents ({len(alerts)})",
        "",
    ]
    for alert in alerts:
        raw = json.dumps(alert.source_ref, default=str, sort_keys=True)
        lines.append(f"### {alert.display_id}: {alert.title or '(untitled)'}")
        lines.append(f"- Severity: {alert.severity or '—'}")
        lines.append(f"- Raw source data: {raw}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(rule, org):
    """Execute rule against OpenSearch for org; materialise alerts and create an Incident.

    Returns the Incident on success, or None if no new findings.
    """
    from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient
    from security.opensearch import OpenSearchClient, OpenSearchError
    from alerts.models import Alert
    from alerts.services.identifiers import next_alert_display_id
    from correlations.models import SearchFinding, SearchFiring
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id
    from incidents.services.ioc_extraction import extract_and_save_iocs
    from incidents.tasks import acquire_triage_lock, enrich_iocs_then_triage

    # Resolve the org's Wazuh agent IDs
    try:
        raw_agents = WazuhClient().get_agents(org.wazuh_group)
        agent_ids = [a["id"] for a in raw_agents]
    except (WazuhAPIError, WazuhAuthError):
        logger.exception("search_evaluator.run: failed to fetch agents for org %s", org.id)
        return None

    if not agent_ids:
        logger.info("search_evaluator.run: org %s has no agents — skipping rule %s", org.id, rule.id)
        return None

    leg = rule.legs.prefetch_related("conditions").first()
    if not leg:
        logger.info("search_evaluator.run: rule %s has no legs — skipping", rule.id)
        return None

    now = timezone.now()
    window_start = now - timedelta(minutes=rule.window_minutes)

    body = compile_query(
        list(leg.conditions.all()),
        agent_ids,
        window_start,
        now,
        rule.max_findings_per_run,
    )

    try:
        result = OpenSearchClient()._search(_ALERTS_INDEX, body)
    except OpenSearchError:
        logger.exception("search_evaluator.run: OpenSearch query failed for rule %s", rule.id)
        return None

    hits = result.get("hits", {}).get("hits", [])
    if not hits:
        return None

    with transaction.atomic():
        new_alerts = []
        for hit in hits:
            doc_id = hit.get("_id", "")
            source_index = hit.get("_index", _ALERTS_INDEX)

            if SearchFinding.objects.filter(
                rule=rule, source_index=source_index, wazuh_doc_id=doc_id
            ).exists():
                continue

            source = hit.get("_source", {})
            agent_name = source.get("agent", {}).get("name", "unknown")
            rule_desc = source.get("rule", {}).get("description", "") or rule.name
            title = f"{rule.name}: {rule_desc}"

            alert = Alert.objects.create(
                organization=org,
                display_id=next_alert_display_id(),
                source_kind="scheduled_search",
                source_ref=source,
                title=title[:255],
                severity=rule.severity,
                state="new",
                description=(
                    f"Matched by scheduled search rule '{rule.name}' on agent '{agent_name}'."
                ),
            )

            SearchFinding.objects.create(
                rule=rule,
                alert=alert,
                source_index=source_index,
                wazuh_doc_id=doc_id,
            )

            new_alerts.append(alert)

        if not new_alerts:
            return None

        description = _compose_description(rule, new_alerts)

        ser = IncidentCreateSerializer(
            data={
                "title": f"{rule.name}: {len(new_alerts)} matching document(s)",
                "severity": rule.severity,
                "source_kind": "scheduled_search",
                "description": description,
                "tlp": "amber",
                "pap": "amber",
            }
        )
        ser.is_valid(raise_exception=True)

        display_id = next_display_id()
        incident = ser.save(organization=org, display_id=display_id, created_by=None)

        record_event(
            incident,
            "incident_created",
            payload={
                "source": "scheduled_search_rule",
                "rule_id": rule.id,
                "rule_name": rule.name,
            },
        )

        for alert in new_alerts:
            alert.state = "imported"
            alert.incident = incident
            alert.save(update_fields=["state", "incident", "updated_at"])
            record_event(
                incident,
                "alert_linked",
                payload={
                    "alert_display_id": alert.display_id,
                    "source": "scheduled_search",
                    "rule_name": rule.name,
                },
            )

        SearchFiring.objects.create(
            rule=rule,
            organization=org,
            incident=incident,
            finding_count=len(new_alerts),
        )

        extract_and_save_iocs(incident)
        if acquire_triage_lock(incident.id):
            incident_id = incident.id
            transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))

    return incident
