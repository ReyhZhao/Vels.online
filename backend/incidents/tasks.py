import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from notifications.email import send_html_email

logger = logging.getLogger(__name__)

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

    tasks = Task.objects.filter(
        task_type=Task.TYPE_AUTOMATED,
        semaphore_task_id__isnull=False,
        state=Task.STATE_IN_PROGRESS,
    )

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
            _notify_task_complete(task)
        elif status in ("error", "failed"):
            Task.objects.filter(pk=task.pk).update(
                state=Task.STATE_NEW,
                automation_error=f"Semaphore job failed with status: {status}",
                semaphore_task_id=None,
            )
            failed += 1

    return {"processed": processed, "done": done, "failed": failed}


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
