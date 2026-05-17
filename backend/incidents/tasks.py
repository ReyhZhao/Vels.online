from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from notifications.email import send_html_email


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
