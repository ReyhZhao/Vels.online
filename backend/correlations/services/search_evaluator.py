"""End-to-end evaluator for Scheduled Search Rules."""
import json
import logging

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from correlations.models import CORRELATION_KEY_NONE
from correlations.services.search_compiler import (
    _ALERTS_INDEX,
    CORRELATION_KEY_TO_WAZUH_FIELD,
    compile_agg_query,
    compile_query,
)

logger = logging.getLogger(__name__)


def _get_mapping_safe() -> dict:
    """Fetch the live field mapping; return {} on any error (used for .keyword resolution)."""
    try:
        from security.opensearch import OpenSearchClient
        return OpenSearchClient().get_field_mapping()
    except Exception:
        return {}


def _distinct_label(field: str) -> str:
    """Friendly label for a diversity field, e.g. GeoLocation.country_name → 'country'."""
    seg = field.rsplit(".", 1)[-1]
    if seg.endswith("_name"):
        seg = seg[: -len("_name")]
    return seg.replace("_", " ") or field


def _format_distinct_title(distinct_info) -> str:
    """One-line spread summary for the incident title, e.g. '3 distinct country (NL, US, RU)'."""
    parts = []
    for field, values in distinct_info.items():
        vals = [str(v) for v, _ in values]
        shown = ", ".join(vals[:10]) + ("…" if len(vals) > 10 else "")
        parts.append(f"{len(vals)} distinct {_distinct_label(field)} ({shown})")
    return "; ".join(parts)


def _compose_description(rule, alerts, key_value=None, distinct_info=None) -> str:
    key_label = f" (key: {key_value})" if key_value and key_value != "none" else ""
    lines = [
        f"Scheduled search rule **{rule.name}** fired{key_label}.",
        f"Description: {rule.description}" if rule.description else "",
        "",
    ]
    if distinct_info:
        lines.append("## Diversity")
        lines.append("")
        for field, values in distinct_info.items():
            lines.append(f"- **{field}** ({len(values)} distinct):")
            for value, count in values:
                lines.append(f"  - {value} ({count})")
        lines.append("")
    lines.append(f"## Matched documents ({len(alerts)})")
    lines.append("")
    for alert in alerts:
        raw = json.dumps(alert.source_ref, default=str, sort_keys=True)
        lines.append(f"### {alert.display_id}: {alert.title or '(untitled)'}")
        lines.append(f"- Severity: {alert.severity or '—'}")
        lines.append(f"- Raw source data: {raw}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _materialise_and_fire(rule, org, hits, key_value="none", overflow=0, distinct_info=None):
    """Persist alerts for *hits* and create/update an Incident for the given key_value.

    - Idempotent: docs already in SearchFinding are skipped.
    - Live-firing dedup: if an open (non-closed) incident already exists for
      (rule, key_value), new findings link into it rather than spawning a sibling.
    - Overflow: when OpenSearch returned fewer hits than its total (truncated by
      max_findings_per_run), an event records "+N more matched (truncated)".

    Returns the Incident, or None if all hits were already seen.
    """
    from alerts.models import Alert
    from alerts.services.identifiers import next_alert_display_id
    from correlations.models import SearchFinding, SearchFiring
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.identifiers import next_display_id
    from incidents.services.ioc_extraction import extract_and_save_iocs
    from incidents.tasks import acquire_triage_lock, enrich_iocs_then_triage

    with transaction.atomic():
        # Live-firing dedup: find an existing open incident for this (rule, key_value).
        live_firing = (
            SearchFiring.objects
            .filter(rule=rule, organization=org, key_value=key_value, incident__isnull=False)
            .exclude(incident__state="closed")
            .select_related("incident")
            .first()
        )

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

        if live_firing:
            # Absorb new findings into the existing open incident.
            incident = live_firing.incident

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

            if overflow > 0:
                record_event(
                    incident,
                    "search_rule_overflow",
                    payload={
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "key_value": key_value,
                        "overflow": overflow,
                        "note": f"+{overflow} more matched (truncated)",
                    },
                )

            SearchFiring.objects.create(
                rule=rule,
                organization=org,
                incident=incident,
                key_value=key_value,
                finding_count=len(new_alerts),
            )

            return incident

        # No live incident — create a fresh one.
        description = _compose_description(rule, new_alerts, key_value, distinct_info)
        if overflow > 0:
            description += f"\n+{overflow} more matched (truncated)\n"

        key_label = f" [{key_value}]" if key_value and key_value != "none" else ""

        if distinct_info:
            title = f"{rule.name}{key_label}: {_format_distinct_title(distinct_info)}"
        else:
            title = f"{rule.name}{key_label}: {len(new_alerts)} matching document(s)"

        ser = IncidentCreateSerializer(
            data={
                "title": title[:255],
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
                "key_value": key_value,
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

        if overflow > 0:
            record_event(
                incident,
                "search_rule_overflow",
                payload={
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "key_value": key_value,
                    "overflow": overflow,
                    "note": f"+{overflow} more matched (truncated)",
                },
            )

        SearchFiring.objects.create(
            rule=rule,
            organization=org,
            incident=incident,
            key_value=key_value,
            finding_count=len(new_alerts),
        )

        extract_and_save_iocs(incident)
        if acquire_triage_lock(incident.id):
            incident_id = incident.id
            transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))

    return incident


def _run_single_leg(rule, org, agent_ids, leg, now, window_start):
    """Degenerate path: one query, one Incident for all matched docs."""
    from security.opensearch import OpenSearchClient, OpenSearchError

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
        logger.exception("search_evaluator: OpenSearch query failed for rule %s", rule.id)
        return None

    hits_block = result.get("hits", {})
    hits = hits_block.get("hits", [])
    if not hits:
        return None

    total_count = hits_block.get("total", {}).get("value", 0)
    overflow = max(0, total_count - len(hits))

    return _materialise_and_fire(rule, org, hits, key_value="none", overflow=overflow)


def _run_multi_leg(rule, org, agent_ids, legs, now, window_start):
    """Multi-leg co-occurrence path via per-leg terms aggregations.

    1. Per leg: run a terms agg on the correlation key field to count docs per key.
    2. Find the intersection: key values where every leg's doc_count >= leg.count.
    3. Per satisfied key: fetch actual docs for all legs and create one Incident.

    Returns the last Incident created, or None.
    """
    from security.opensearch import OpenSearchClient, OpenSearchError

    wazuh_field = CORRELATION_KEY_TO_WAZUH_FIELD[rule.correlation_key]

    # Mapping is needed only to resolve .keyword for any leg's diversity field.
    mapping = _get_mapping_safe() if any(leg.has_diversity for leg in legs) else {}

    # Step 1: per-leg agg to find which key values satisfy each leg's thresholds.
    #   - doc_count >= leg.count (always), AND
    #   - distinct(distinct_field) >= leg.min_distinct (Diversity Constraint, ADR-0009).
    # distinct_by_leg[leg.id][key] = [(value, doc_count), ...] for legs with a diversity constraint.
    satisfied_keys = None
    distinct_by_leg: dict = {}
    for leg in legs:
        agg_body = compile_agg_query(
            list(leg.conditions.all()),
            agent_ids,
            window_start,
            now,
            wazuh_field,
            field_mapping=mapping,
            distinct_field=leg.distinct_field or None,
        )
        try:
            result = OpenSearchClient()._search(_ALERTS_INDEX, agg_body)
        except OpenSearchError:
            logger.exception(
                "search_evaluator: agg query failed for rule %s leg %s", rule.id, leg.id
            )
            return None

        buckets = result.get("aggregations", {}).get("key_agg", {}).get("buckets", [])
        leg_satisfied = set()
        for b in buckets:
            if b["doc_count"] < leg.count:
                continue
            if leg.has_diversity:
                d_buckets = b.get("distinct_agg", {}).get("buckets", [])
                if len(d_buckets) < leg.min_distinct:
                    continue
                distinct_by_leg.setdefault(leg.id, {})[b["key"]] = [
                    (db["key"], db["doc_count"]) for db in d_buckets
                ]
            leg_satisfied.add(b["key"])

        if satisfied_keys is None:
            satisfied_keys = leg_satisfied
        else:
            satisfied_keys &= leg_satisfied  # intersection: all legs must fire for the same key

    if not satisfied_keys:
        return None

    # Step 2: for each satisfied key fetch the actual documents and materialise an Incident.
    last_incident = None
    for key_value in sorted(satisfied_keys):
        all_hits = []
        total_overflow = 0
        for leg in legs:
            body = compile_query(
                list(leg.conditions.all()),
                agent_ids,
                window_start,
                now,
                rule.max_findings_per_run,
                key_field=wazuh_field,
                key_value=key_value,
                field_mapping=mapping,
            )
            try:
                result = OpenSearchClient()._search(_ALERTS_INDEX, body)
                hits_block = result.get("hits", {})
                leg_hits = hits_block.get("hits", [])
                leg_total = hits_block.get("total", {}).get("value", 0)
                all_hits.extend(leg_hits)
                total_overflow += max(0, leg_total - len(leg_hits))
            except OpenSearchError:
                logger.exception(
                    "search_evaluator: hit fetch failed for rule %s key %r", rule.id, key_value
                )
                continue

        # Merge the per-leg distinct values for this key (across all diversity legs).
        distinct_info: dict = {}
        for leg in legs:
            per_key = distinct_by_leg.get(leg.id, {})
            if key_value in per_key:
                distinct_info.setdefault(leg.distinct_field, []).extend(per_key[key_value])

        if all_hits:
            incident = _materialise_and_fire(
                rule, org, all_hits, key_value=key_value, overflow=total_overflow,
                distinct_info=distinct_info or None,
            )
            if incident:
                last_incident = incident

    return last_incident


def debug_run(rule, org) -> dict:
    """Execute rule queries against OpenSearch for org WITHOUT materialising any results.

    Returns a dict describing the queries sent and raw OpenSearch responses, for
    troubleshooting purposes.  No alerts, incidents, or SearchFinding records are created.
    """
    from security.opensearch import OpenSearchClient, OpenSearchError
    from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

    try:
        raw_agents = WazuhClient().get_agents(org.wazuh_group)
        agent_ids = [a["id"] for a in raw_agents]
    except (WazuhAPIError, WazuhAuthError) as exc:
        return {"error": f"Failed to fetch agents: {exc}"}

    if not agent_ids and not rule.include_agentless:
        return {"error": f"Org '{org.slug}' has no Wazuh agents."}

    # None tells the compiler to omit the agent.id filter entirely.
    effective_agent_ids = None if rule.include_agentless else agent_ids

    legs = list(rule.legs.prefetch_related("conditions"))
    if not legs:
        return {"error": "Rule has no legs."}

    now = timezone.now()
    window_start = now - timedelta(minutes=rule.window_minutes)

    has_diversity = any(leg.has_diversity for leg in legs)
    use_multi = rule.correlation_key != CORRELATION_KEY_NONE and (len(legs) > 1 or has_diversity)
    wazuh_field = CORRELATION_KEY_TO_WAZUH_FIELD.get(rule.correlation_key)
    mapping = _get_mapping_safe() if has_diversity else {}

    client = OpenSearchClient()
    result = {
        "mode": "multi" if use_multi else "single",
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "agent_count": len(agent_ids),
        "include_agentless": rule.include_agentless,
        "legs": [],
    }

    for leg in legs:
        leg_entry: dict = {"leg_id": leg.id, "display_order": leg.display_order, "count": leg.count}
        conditions = list(leg.conditions.all())

        if use_multi:
            agg_body = compile_agg_query(
                conditions, effective_agent_ids, window_start, now, wazuh_field,
                field_mapping=mapping, distinct_field=leg.distinct_field or None,
            )
            leg_entry["agg_query"] = agg_body
            try:
                agg_response = client._search(_ALERTS_INDEX, agg_body)
                leg_entry["agg_response"] = agg_response
            except OpenSearchError as exc:
                leg_entry["agg_error"] = str(exc)

        hit_body = compile_query(conditions, effective_agent_ids, window_start, now, rule.max_findings_per_run)
        leg_entry["hit_query"] = hit_body
        try:
            hit_response = client._search(_ALERTS_INDEX, hit_body)
            leg_entry["hit_response"] = hit_response
        except OpenSearchError as exc:
            leg_entry["hit_error"] = str(exc)

        result["legs"].append(leg_entry)

    return result


def run(rule, org):
    """Execute rule against OpenSearch for org; materialise alerts and create Incident(s).

    For rules with correlation_key != "none" and multiple legs: runs the multi-leg
    co-occurrence path — one Incident per satisfied key.  Otherwise uses the simpler
    single-leg path that produces one Incident for all matched documents.

    Returns the last Incident created on success, or None if no new findings.
    """
    from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

    try:
        raw_agents = WazuhClient().get_agents(org.wazuh_group)
        agent_ids = [a["id"] for a in raw_agents]
    except (WazuhAPIError, WazuhAuthError):
        logger.exception("search_evaluator.run: failed to fetch agents for org %s", org.id)
        return None

    if not agent_ids and not rule.include_agentless:
        logger.info("search_evaluator.run: org %s has no agents — skipping rule %s", org.id, rule.id)
        return None

    # None tells the compiler to omit the agent.id filter entirely.
    effective_agent_ids = None if rule.include_agentless else agent_ids

    legs = list(rule.legs.prefetch_related("conditions"))
    if not legs:
        logger.info("search_evaluator.run: rule %s has no legs — skipping", rule.id)
        return None

    now = timezone.now()
    window_start = now - timedelta(minutes=rule.window_minutes)

    # The aggregation path is required for multi-leg co-occurrence AND for any rule whose
    # leg carries a Diversity Constraint (single-leg impossible-travel routes here too).
    has_diversity = any(leg.has_diversity for leg in legs)
    use_multi = rule.correlation_key != CORRELATION_KEY_NONE and (len(legs) > 1 or has_diversity)

    if use_multi:
        return _run_multi_leg(rule, org, effective_agent_ids, legs, now, window_start)
    else:
        return _run_single_leg(rule, org, effective_agent_ids, legs[0], now, window_start)
