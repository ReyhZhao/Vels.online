from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .email import send_html_email


@shared_task
def send_digest_email(recipient_id, incident_id):
    try:
        recipient = User.objects.get(pk=recipient_id)
    except User.DoesNotExist:
        return

    if not recipient.email:
        return

    from notifications.models import Notification

    qs = Notification.objects.filter(recipient=recipient, email_sent_at__isnull=True)
    if incident_id is not None:
        qs = qs.filter(incident_id=incident_id)

    notifications = list(qs.select_related("incident").order_by("created_at"))
    if not notifications:
        return

    items = [
        {
            "title": n.payload.get("title", f"Notification: {n.kind}"),
            "body": n.payload.get("body", ""),
            "link": n.payload.get("link", ""),
        }
        for n in notifications
    ]

    send_html_email(
        "notification_digest",
        {
            "recipient_name": recipient.get_full_name() or recipient.username,
            "count": len(notifications),
            "items": items,
            "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
        },
        [recipient.email],
    )

    now = timezone.now()
    for n in notifications:
        n.email_sent_at = now
    Notification.objects.bulk_update(notifications, ["email_sent_at"])


@shared_task
def cleanup_old_notifications():
    from datetime import timedelta
    from notifications.models import Notification
    cutoff = timezone.now() - timedelta(hours=24)
    Notification.objects.filter(created_at__lt=cutoff).delete()
