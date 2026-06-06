import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

_RESIDUAL_SETTLE_MINUTES = 15


@shared_task(name="correlations.tasks.run_scheduled_search_rule")
def run_scheduled_search_rule(rule_id: int):
    """Run a SearchRule against OpenSearch.

    Org rule: run once for rule.organization.
    System rule (organization=None): fan out across all orgs, skipping muted orgs.
    Each org is wrapped so one org's failure does not abort the rest.
    """
    from correlations.models import SearchRule, SearchRuleMute
    from correlations.services.search_evaluator import run
    from security.models import Organization

    try:
        rule = SearchRule.objects.select_related("organization").prefetch_related("legs__conditions").get(id=rule_id)
    except SearchRule.DoesNotExist:
        logger.warning("run_scheduled_search_rule: rule %s not found", rule_id)
        return

    if not rule.enabled:
        return

    if rule.organization_id is not None:
        try:
            run(rule, rule.organization)
        except Exception:
            logger.exception("run_scheduled_search_rule: failed for rule %s", rule_id)
        return

    muted_org_ids = set(
        SearchRuleMute.objects.filter(rule=rule).values_list("organization_id", flat=True)
    )
    for org in Organization.objects.all():
        if org.id in muted_org_ids:
            logger.debug("run_scheduled_search_rule: org %s muted rule %s — skipping", org.id, rule_id)
            continue
        try:
            run(rule, org)
        except Exception:
            logger.exception(
                "run_scheduled_search_rule: failed for rule %s org %s — continuing", rule_id, org.id
            )
_RESIDUAL_LOOKBACK_HOURS = 24
_RESIDUAL_CONFIDENCE_THRESHOLD = 0.6
_RESIDUAL_BATCH_LIMIT = 200


@shared_task
def evaluate_correlation_rules(alert_id: int):
    """Evaluate all enabled correlation rules against the given alert.

    Enqueued on transaction.on_commit after alert creation so it always
    runs against a fully committed alert (including its entities).
    """
    from alerts.models import Alert
    from correlations.services.evaluator import evaluate

    try:
        alert = Alert.objects.select_related("organization").prefetch_related("entities").get(
            id=alert_id
        )
    except Alert.DoesNotExist:
        logger.warning("evaluate_correlation_rules: alert %s not found", alert_id)
        return

    if alert.source_kind == "scheduled_search":
        return  # Materialised search-alerts participate only in their own SearchRule incident

    evaluate(alert)


@shared_task
def run_residual_safety_net():
    """Periodic LLM safety-net over residual (unlinked, settled) alerts.

    Runs per organisation; alerts aged past the settle delay but within the
    lookback window are grouped by the LLM and emitted as DetectionSuggestion
    records for analyst review.
    """
    from security.models import Organization

    for org in Organization.objects.all():
        try:
            _run_residual_for_org(org)
        except Exception:
            logger.exception("run_residual_safety_net: failed for org %s", org.id)


def _alert_to_payload(alert) -> dict:
    entities = [{"type": e.entity_type, "value": e.value} for e in alert.entities.all()]
    return {
        "id": alert.id,
        "title": alert.title or "",
        "severity": alert.severity or "",
        "source_kind": alert.source_kind or "",
        "entities": entities,
    }


def _derive_severity(alerts) -> str:
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    rank_to_sev = {v: k for k, v in rank.items()}
    max_rank = max((rank.get(a.severity, 0) for a in alerts), default=0)
    return rank_to_sev.get(max_rank, "medium")


def _create_incident_from_suggestion(suggestion):
    from django.db import transaction
    from incidents.models import Incident
    from incidents.serializers import IncidentCreateSerializer
    from incidents.services.events import record_event
    from incidents.services.ioc_extraction import extract_and_save_iocs
    from incidents.services.identifiers import next_display_id
    from incidents.tasks import acquire_triage_lock, enrich_iocs_then_triage
    from correlations.models import DetectionSuggestion

    alerts = list(suggestion.proposed_alerts.select_related("organization").all())
    if not alerts:
        return None

    severity = _derive_severity(alerts)
    title = f"LLM Detection: {suggestion.rationale[:100]}"

    with transaction.atomic():
        ser = IncidentCreateSerializer(data={
            "title": title,
            "severity": severity,
            "source_kind": "correlation",
            "description": suggestion.rationale,
            "tlp": "amber",
            "pap": "amber",
        })
        ser.is_valid(raise_exception=True)
        display_id = next_display_id()
        incident = ser.save(
            organization=suggestion.organization,
            display_id=display_id,
            created_by=None,
        )

        record_event(
            incident,
            "incident_created",
            payload={"source": "llm_detection_suggestion", "suggestion_id": suggestion.id},
        )

        for alert in alerts:
            alert.state = "imported"
            alert.incident = incident
            alert.save(update_fields=["state", "incident", "updated_at"])
            record_event(
                incident,
                "alert_linked",
                payload={
                    "alert_display_id": alert.display_id,
                    "source": "llm_detection_suggestion",
                },
            )

        suggestion.status = DetectionSuggestion.STATUS_ACCEPTED
        suggestion.incident = incident
        suggestion.save(update_fields=["status", "incident", "updated_at"])

        extract_and_save_iocs(incident)
        if acquire_triage_lock(incident.id):
            incident_id = incident.id
            transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))

    return incident


def _run_residual_for_org(org):
    from alerts.models import Alert
    from correlations.models import DetectionSuggestion
    from incidents.llm.base import TriageConfigError, TriageError
    from incidents.llm.factory import get_triage_provider

    now = timezone.now()
    settle_cutoff = now - timedelta(minutes=_RESIDUAL_SETTLE_MINUTES)
    lookback_cutoff = now - timedelta(hours=_RESIDUAL_LOOKBACK_HOURS)

    residuals = list(
        Alert.objects.filter(
            organization=org,
            state="new",
            incident__isnull=True,
            created_at__gte=lookback_cutoff,
            created_at__lte=settle_cutoff,
        ).prefetch_related("entities")[:_RESIDUAL_BATCH_LIMIT]
    )

    if not residuals:
        return

    alert_payloads = [_alert_to_payload(a) for a in residuals]

    try:
        provider = get_triage_provider()
    except TriageConfigError:
        logger.debug("run_residual_safety_net: LLM provider not configured, skipping org %s", org.id)
        return

    try:
        result = provider.group_residual_alerts(alert_payloads)
    except TriageError:
        logger.exception("_run_residual_for_org: LLM grouping failed for org %s", org.id)
        return

    alert_by_id = {a.id: a for a in residuals}

    for group in result.groups:
        if group.confidence < _RESIDUAL_CONFIDENCE_THRESHOLD:
            continue

        matched = [alert_by_id[aid] for aid in group.alert_ids if aid in alert_by_id]
        if len(matched) < 2:
            continue

        suggestion = DetectionSuggestion.objects.create(
            organization=org,
            rationale=group.rationale,
            confidence=group.confidence,
        )
        suggestion.proposed_alerts.set(matched)

        if (
            org.llm_residual_autocreate_threshold is not None
            and group.confidence >= org.llm_residual_autocreate_threshold
        ):
            try:
                _create_incident_from_suggestion(suggestion)
            except Exception:
                logger.exception(
                    "_run_residual_for_org: auto-create failed for suggestion %s", suggestion.id
                )
