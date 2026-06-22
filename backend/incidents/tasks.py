import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from incidents.llm.base import RANK_TO_SEV, SEVERITY_RANK, TriageConfigError, TriageError
from incidents.llm.factory import get_closure_provider, get_triage_provider
from notifications.email import send_html_email

logger = logging.getLogger(__name__)

_TRIAGE_LOCK_KEY = "triage_lock:{}"
_TRIAGE_LOCK_TTL = 600  # 10 minutes
_CORRELATION_THRESHOLD = 0.7
_CORRELATION_LOOKBACK_DAYS = 30
_CORRELATION_CANDIDATE_LIMIT = 50


def acquire_triage_lock(incident_id: int) -> bool:
    """Atomically set the triage lock.  Returns True if the lock was acquired."""
    started_at = timezone.now().isoformat()
    return cache.add(_TRIAGE_LOCK_KEY.format(incident_id), started_at, _TRIAGE_LOCK_TTL)


def release_triage_lock(incident_id: int) -> None:
    cache.delete(_TRIAGE_LOCK_KEY.format(incident_id))


def get_triage_lock_started_at(incident_id: int) -> str | None:
    """Return the ISO-format start timestamp if triage is running, else None."""
    return cache.get(_TRIAGE_LOCK_KEY.format(incident_id))


@shared_task
def notify_contacts_on_close(incident_id: int):
    """Send an LLM-generated closure notification to all IncidentContacts for a closed incident."""
    from incidents.models import Comment, Incident
    from contacts.services import send_contact_message

    try:
        incident = Incident.objects.select_related("organization").get(id=incident_id)
    except Incident.DoesNotExist:
        return

    incident_contacts = list(incident.incident_contacts.select_related("contact").all())
    if not incident_contacts:
        return

    ai_summaries = list(
        Comment.objects.filter(incident=incident, kind=Comment.KIND_AI_TRIAGE)
        .order_by("created_at")
        .values_list("body", flat=True)
    )
    incident_context = {
        "title": incident.title,
        "severity": incident.severity,
        "description": incident.description or "",
        "closure_reason": incident.closure_reason or "",
        "ai_triage_summaries": ai_summaries,
    }

    try:
        provider = get_closure_provider()
        message_body = provider.generate_closure_message(incident_context)
    except Exception as exc:
        logger.warning(
            "notify_contacts_on_close: LLM call failed for incident %s: %s", incident_id, exc
        )
        return

    if not message_body:
        logger.warning(
            "notify_contacts_on_close: LLM returned empty message for incident %s", incident_id
        )
        return

    for ic in incident_contacts:
        try:
            send_contact_message(incident, ic.contact, role="notified", body=message_body)
        except Exception as exc:
            logger.warning(
                "notify_contacts_on_close: failed to notify contact %s for incident %s: %s",
                ic.contact.id, incident_id, exc,
            )


def _clamp_severity(current: str, recommended: str) -> str:
    """Return the recommended severity clamped to at most 2 rank levels from the current."""
    current_rank = SEVERITY_RANK.get(current, 2)
    recommended_rank = SEVERITY_RANK.get(recommended, current_rank)
    delta = recommended_rank - current_rank
    if delta == 0:
        return current
    capped_rank = current_rank + max(-2, min(2, delta))
    return RANK_TO_SEV.get(capped_rank, current)


@shared_task
def enrich_iocs_then_triage(incident_id: int):
    """Coordinator: enrich all IOCs then dispatch triage.

    Currently a pass-through; enrichment logic is added in subsequent slices.
    """
    from incidents.services.ioc_enrichment import enrich_ioc
    from incidents.models import IOC

    for ioc in IOC.objects.filter(incident_id=incident_id):
        try:
            result = enrich_ioc(ioc)
            if result:
                ioc.enrichment_data = result
                ioc.save(update_fields=["enrichment_data"])
        except Exception as exc:
            logger.warning("enrich_iocs_then_triage: enrichment failed for IOC %s: %s", ioc.id, exc)

    run_incident_triage.delay(incident_id)


@shared_task(bind=True, max_retries=3)
def run_incident_triage(self, incident_id: int):
    from incidents.models import Comment, Incident
    from incidents.services.transitions import ALLOWED_TRANSITIONS, transition_incident

    try:
        incident = Incident.objects.select_related("organization").prefetch_related(
            "incident_assets__asset", "iocs"
        ).get(id=incident_id)
    except Incident.DoesNotExist:
        release_triage_lock(incident_id)
        return

    payload = _build_triage_payload(incident)
    extra_context = incident.organization.triage_prompt_context or ""

    try:
        provider = get_triage_provider()
        result = provider.triage_incident(payload, extra_context=extra_context)
    except TriageConfigError as exc:
        release_triage_lock(incident_id)
        Comment.objects.create(
            incident=incident,
            kind=Comment.KIND_SYSTEM,
            body=f"AI triage is misconfigured and cannot run: {exc}",
            is_internal=True,
        )
        return
    except TriageError as exc:
        if self.request.retries >= self.max_retries:
            release_triage_lock(incident_id)
            Comment.objects.create(
                incident=incident,
                kind=Comment.KIND_SYSTEM,
                body=f"AI triage could not be completed after {self.max_retries + 1} attempts. Last error: {exc}",
                is_internal=True,
            )
            return
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            release_triage_lock(incident_id)
            Comment.objects.create(
                incident=incident,
                kind=Comment.KIND_SYSTEM,
                body=f"AI triage failed unexpectedly after {self.max_retries + 1} attempts. Last error: {exc}",
                is_internal=True,
            )
            return
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    release_triage_lock(incident_id)

    # Related incident correlation search (best-effort — failures do not block triage)
    related_incident_ids = []
    correlation_summary = ""
    try:
        candidates = _build_correlation_candidates(incident)
        if candidates:
            correlation = provider.find_related_incidents(payload, candidates)
            if correlation.max_confidence >= _CORRELATION_THRESHOLD and correlation.related_incident_ids:
                related_incident_ids = correlation.related_incident_ids
                correlation_summary = correlation.correlation_summary
                related_context = _build_related_context(related_incident_ids, correlation_summary)
                augmented_context = "\n".join(filter(None, [extra_context, related_context]))
                result = provider.triage_incident(payload, extra_context=augmented_context)
    except Exception as exc:
        logger.warning("run_incident_triage: correlation search failed for %s: %s", incident_id, exc)

    threshold = incident.organization.triage_fp_threshold
    auto_closed = result.false_positive_confidence >= threshold

    if auto_closed:
        try:
            transition_incident(incident, "closed", actor=None, closure_reason="false_positive")
        except Exception as exc:
            logger.warning("run_incident_triage: auto-close failed for %s: %s", incident_id, exc)
            auto_closed = False

    if not auto_closed and "triaged" in ALLOWED_TRANSITIONS.get(incident.state, set()):
        try:
            transition_incident(incident, "triaged", actor=None)
            from oncall.services.routing import route_triaged_incident
            route_triaged_incident(incident, result)
        except Exception as exc:
            logger.warning("run_incident_triage: state transition to triaged failed for %s: %s", incident_id, exc)

    new_severity = _clamp_severity(incident.severity, result.severity_recommendation)
    if new_severity != incident.severity:
        incident.severity = new_severity
        incident.save(update_fields=["severity"])

    if not auto_closed and result.subject_recommendation and incident.subject_id is None:
        from incidents.models import Subject
        try:
            subject = Subject.objects.get(slug=result.subject_recommendation)
            incident.subject = subject
            incident.save(update_fields=["subject"])
        except Subject.DoesNotExist:
            logger.warning("run_incident_triage: subject slug %r not found for %s", result.subject_recommendation, incident_id)

    Comment.objects.create(
        incident=incident,
        kind=Comment.KIND_AI_TRIAGE,
        author=None,
        body=result.summary,
        is_internal=True,
        metadata={
            "severity_recommendation": result.severity_recommendation,
            "primary_action": result.primary_action,
            "secondary_action": result.secondary_action,
            "false_positive_confidence": result.false_positive_confidence,
            "disposition_confidence": result.disposition_confidence,
            "subject_recommendation": result.subject_recommendation,
            "provider": result.provider,
            "incident_severity_at_triage": payload["severity"],
            "auto_closed": auto_closed,
            "related_incident_ids": related_incident_ids,
            "correlation_summary": correlation_summary,
        },
    )

    # Gate (ADR-0024): on high disposition confidence with a matched subject, hand off
    # to the agentic Triage Work phase as a background job.
    if not auto_closed:
        from incidents.triage_agent import should_run_work_phase
        incident.refresh_from_db(fields=["subject", "triage_worked_at"])
        if should_run_work_phase(incident, result):
            run_triage_work_task.delay(incident.id)


@shared_task
def run_triage_work_task(incident_id: int):
    """Celery entry for the agentic Triage Work phase (ADR-0024)."""
    from incidents.triage_agent import run_triage_work
    run_triage_work(incident_id)


def _ioc_enrichment_annotation(ioc) -> str | None:
    """Return a compact enrichment annotation string for the IOC, or None if unavailable."""
    if ioc.kind == "email":
        return ioc.value
    data = ioc.enrichment_data
    if not data:
        return None
    if ioc.kind == "ip":
        ab = data.get("abuseipdb", {})
        if ab.get("status") != "done":
            return None
        parts = [f"AbuseIPDB: {ab['abuse_confidence_score']}/100"]
        if ab.get("total_reports") is not None:
            parts.append(f"{ab['total_reports']} reports")
        if ab.get("usage_type"):
            parts.append(ab["usage_type"])
        if ab.get("country_code"):
            parts.append(ab["country_code"])
        return f"{ioc.value} ({', '.join(parts)})"
    if ioc.kind in ("domain", "url"):
        vt = data.get("virustotal", {})
        if vt.get("status") != "done":
            return None
        return f"{ioc.value} (VirusTotal: {vt['malicious']}/{vt['total']} engines malicious)"
    return None


def _build_triage_payload(incident) -> dict:
    assets = [
        {
            "name": ia.asset.name,
            "kind": ia.asset.kind,
            "agent_name": ia.asset.agent_name,
            "ip_address": str(ia.asset.ip_address) if ia.asset.ip_address else None,
        }
        for ia in incident.incident_assets.all()
    ]
    iocs = []
    for ioc in incident.iocs.all():
        annotation = _ioc_enrichment_annotation(ioc)
        iocs.append({"kind": ioc.kind, "value": annotation or ioc.value})
    return {
        "source_kind": incident.source_kind,
        "source_ref": incident.source_ref,
        "assets": assets,
        "iocs": iocs,
        "title": incident.title,
        "description": incident.description,
        "severity": incident.severity,
    }


def build_triage_prompts(incident) -> tuple:
    """Return (system_prompt, user_payload_json) for the given incident. Used by the debug view."""
    import json as _json
    from incidents.llm.gemini import _build_system_prompt
    payload = _build_triage_payload(incident)
    extra_context = incident.organization.triage_prompt_context or ""
    system_prompt = _build_system_prompt(payload.get("source_kind", ""), extra_context)
    return system_prompt, _json.dumps(payload, indent=2)

def _build_correlation_candidates(incident) -> list:
    """Return summary dicts for recent non-current incidents in the same org."""
    from incidents.models import Incident
    cutoff = timezone.now() - timedelta(days=_CORRELATION_LOOKBACK_DAYS)
    recent = (
        Incident.objects
        .filter(organization=incident.organization, created_at__gte=cutoff)
        .exclude(pk=incident.pk)
        .exclude(closure_reason=Incident.CLOSURE_FALSE_POSITIVE)
        .prefetch_related("incident_assets__asset", "iocs")
        [:_CORRELATION_CANDIDATE_LIMIT]
    )
    return [
        {
            "id": inc.id,
            "title": inc.title,
            "assets": [
                {
                    "name": ia.asset.name,
                    "agent_name": ia.asset.agent_name,
                    "ip_address": str(ia.asset.ip_address) if ia.asset.ip_address else None,
                }
                for ia in inc.incident_assets.all()
            ],
            "iocs": [{"kind": ioc.kind, "value": ioc.value} for ioc in inc.iocs.all()],
            "severity": inc.severity,
            "created_at": inc.created_at.isoformat(),
        }
        for inc in recent
    ]


def _build_related_context(related_ids: list, correlation_summary: str) -> str:
    if not related_ids:
        return ""
    from incidents.models import Incident
    related = list(Incident.objects.filter(id__in=related_ids).only("display_id", "title", "severity"))
    lines = ["Related incidents detected:"]
    for inc in related:
        lines.append(f"  - {inc.display_id}: {inc.title} ({inc.severity})")
    if correlation_summary:
        lines.append(f"Correlation: {correlation_summary}")
    return "\n".join(lines)


STALE_INCIDENT_DAYS = 7
STALE_INCIDENT_STATES = ["new", "triaged", "resolved"]


@shared_task
def auto_close_stale_incidents():
    """Close incidents in new/triaged/resolved states that are older than STALE_INCIDENT_DAYS."""
    from incidents.models import Incident
    from incidents.services.events import record_event

    cutoff = timezone.now() - timedelta(days=STALE_INCIDENT_DAYS)
    stale = Incident.objects.filter(state__in=STALE_INCIDENT_STATES, created_at__lt=cutoff)

    closed = 0
    for incident in stale:
        incident.state = Incident.STATE_CLOSED
        incident.save(update_fields=["state"])
        record_event(incident, "auto_closed", payload={"reason": f"stale after {STALE_INCIDENT_DAYS} days"})
        closed += 1

    return {"closed": closed}


@shared_task
def poll_automated_tasks():
    from automations.semaphore import SemaphoreAPIError, SemaphoreClient
    from incidents.models import Task

    tasks = list(Task.objects.filter(
        task_type=Task.TYPE_AUTOMATED,
        semaphore_task_id__isnull=False,
        state=Task.STATE_IN_PROGRESS,
    ))

    if not tasks:
        return {"processed": 0, "done": 0, "failed": 0}

    processed = done = failed = 0
    client = SemaphoreClient()

    for task in tasks:
        processed += 1
        try:
            status = client.get_job_status(task.semaphore_task_id)
        except (SemaphoreAPIError, Exception) as exc:
            logger.error("poll_automated_tasks: error polling task %s: %s", task.id, exc)
            continue

        if status == "success":
            Task.objects.filter(pk=task.pk).update(
                state=Task.STATE_DONE,
                closed_at=timezone.now(),
                automation_error=None,
            )
            done += 1
            _create_task_summary_comment(task, client)
            _notify_task_complete(task)
        elif status in ("error", "failed"):
            Task.objects.filter(pk=task.pk).update(
                state=Task.STATE_NEW,
                automation_error=f"Semaphore job failed with status: {status}",
                semaphore_task_id=None,
            )
            failed += 1
            _create_task_summary_comment(task, client, failed=True)

    return {"processed": processed, "done": done, "failed": failed}


def _create_task_summary_comment(task, client, failed=False):
    """Fetch task output from Semaphore, summarise with LLM, and post as a task comment."""
    from incidents.llm.base import TriageConfigError, TriageError
    from incidents.models import Comment

    try:
        raw_output = client.get_job_output(task.semaphore_task_id)
    except Exception as exc:
        logger.warning("_create_task_summary_comment: failed to fetch output for task %s: %s", task.id, exc)
        return

    if not raw_output and not failed:
        return

    # Fall back to a plain system comment if LLM is unavailable
    summary_body = None
    findings = []
    llm_status = "error" if failed else "success"
    provider = ""

    if raw_output:
        try:
            provider_instance = get_triage_provider()
            result = provider_instance.summarize_task_output(task.title, raw_output)
            summary_body = result.summary
            findings = result.findings
            llm_status = result.status
            provider = result.provider
        except (TriageConfigError, TriageError, Exception) as exc:
            logger.warning("_create_task_summary_comment: LLM summarisation failed for task %s: %s", task.id, exc)

    if not summary_body:
        summary_body = (
            f"Automated task {'failed' if failed else 'completed'}. "
            f"Output ({len(raw_output)} chars) could not be summarised by the AI."
            if raw_output
            else f"Automated task {'failed' if failed else 'completed'} with no output."
        )

    Comment.objects.create(
        incident=task.incident,
        task=task,
        kind=Comment.KIND_AI_TASK_SUMMARY,
        author=None,
        body=summary_body,
        is_internal=True,
        metadata={
            "findings": findings,
            "status": llm_status,
            "provider": provider,
            "raw_output_length": len(raw_output),
        },
    )


def _notify_task_complete(task):
    from incidents.models import IncidentDelegation
    from notifications.services.notifications import notify

    incident = task.incident
    recipients = []

    if incident.assignee_id:
        try:
            from django.contrib.auth.models import User
            recipients.append(User.objects.get(pk=incident.assignee_id))
        except Exception:
            pass

    delegate_ids = IncidentDelegation.objects.filter(
        incident=incident, returned_at__isnull=True
    ).values_list("user_id", flat=True)
    from django.contrib.auth.models import User
    delegates = list(User.objects.filter(id__in=delegate_ids))
    all_recipients = list({u.id: u for u in recipients + delegates}.values())

    if all_recipients:
        notify(
            "task_complete",
            all_recipients,
            incident=incident,
            task=task,
            payload={
                "title": f"Automated task completed: {task.title}",
                "body": f"{incident.display_id} — {task.title}",
                "link": f"/incidents/{incident.display_id}",
            },
        )


@shared_task
def send_assigned_incidents_digest():
    from incidents.models import Incident, IncidentEvent

    ACTIVE_STATES = [
        Incident.STATE_NEW,
        Incident.STATE_TRIAGED,
        Incident.STATE_IN_PROGRESS,
        Incident.STATE_ON_HOLD,
        Incident.STATE_NEEDS_TUNING,
        # pending_closure still needs the assignee's ratification, so it stays in the
        # assigned-incidents digest (ADR-0025).
        Incident.STATE_PENDING_CLOSURE,
    ]
    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    since = timezone.now() - timedelta(hours=24)

    incidents = (
        Incident.objects
        .filter(assignee__isnull=False, state__in=ACTIVE_STATES)
        .select_related("assignee")
    )

    by_assignee = defaultdict(list)
    for incident in incidents:
        by_assignee[incident.assignee].append(incident)

    sent = 0
    skipped = 0

    for assignee, assigned_list in by_assignee.items():
        if not assignee.email:
            skipped += 1
            continue

        assigned_list.sort(key=lambda i: SEVERITY_ORDER.get(i.severity, 99))
        incident_ids = [i.id for i in assigned_list]

        recent_events = list(
            IncidentEvent.objects
            .filter(incident_id__in=incident_ids, created_at__gte=since)
            .select_related("incident", "actor")
            .order_by("incident_id", "created_at")
        )

        count = len(assigned_list)
        noun = "incident" if count == 1 else "incidents"

        send_html_email(
            "incident_digest",
            {
                "assignee_name": assignee.get_full_name() or assignee.username,
                "count": count,
                "noun": noun,
                "incidents": [
                    {
                        "display_id": inc.display_id,
                        "title": inc.title,
                        "severity": inc.severity,
                        "state": inc.get_state_display(),
                        "url": f"{frontend_url}/incidents/{inc.display_id}",
                    }
                    for inc in assigned_list
                ],
                "recent_events": [
                    {
                        "display_id": ev.incident.display_id,
                        "kind": ev.kind,
                        "actor": (
                            ev.actor.get_full_name() or ev.actor.username
                            if ev.actor else "System"
                        ),
                    }
                    for ev in recent_events
                ],
                "frontend_url": frontend_url,
            },
            [assignee.email],
        )
        sent += 1

    return {"sent": sent, "skipped": skipped}


@shared_task
def cleanup_orphaned_attachments():
    """Remove S3 objects under incidents/ that have no Attachment row and are older than 24h."""
    from security.storage import StorageClient
    from incidents.models import Attachment

    client = StorageClient()
    cutoff = datetime.now(dt_timezone.utc) - timedelta(hours=24)
    existing_keys = set(Attachment.objects.values_list("s3_key", flat=True))

    for obj in client.list_objects("incidents/"):
        if obj["Key"] not in existing_keys and obj["LastModified"] < cutoff:
            client.delete_file(obj["Key"])


@shared_task
def sync_wazuh_agents():
    import os

    from security.models import Organization
    from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient
    from incidents.models import Asset

    stale_days = int(os.environ.get("ASSET_STALE_DAYS", 30))
    now = timezone.now()

    for org in Organization.objects.tenants():
        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
        except (WazuhAuthError, WazuhAPIError) as exc:
            logger.exception("sync_wazuh_agents failed for org %s: %s", org.slug, exc)
            continue

        seen_agent_names = set()
        for agent in raw_agents:
            agent_name = agent.get("name")
            if not agent_name:
                continue
            seen_agent_names.add(agent_name)
            ip_address = agent.get("ip") or None
            Asset.objects.update_or_create(
                organization=org,
                kind=Asset.KIND_HOST,
                agent_name=agent_name,
                defaults={
                    "name": agent_name,
                    "ip_address": ip_address,
                    "is_active": True,
                    "last_seen_at": now,
                },
            )

        Asset.objects.filter(
            organization=org,
            kind=Asset.KIND_HOST,
        ).exclude(agent_name__in=seen_agent_names).update(is_active=False)

    cutoff = now - timedelta(days=stale_days)
    deleted, _ = Asset.objects.filter(
        kind=Asset.KIND_HOST,
        last_seen_at__lt=cutoff,
        is_permanent=False,
    ).delete()
    logger.info("sync_wazuh_agents: deleted %d stale assets", deleted)
