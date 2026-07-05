import json

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
def send_push_notifications(user_id, payload_dict):
    from pywebpush import webpush, WebPushException
    from .models import Notification, PushSubscription

    # Carry the recipient's current unread in-app count so the service worker can set
    # the OS app-icon badge (iOS Badging API needs an absolute value; it never
    # auto-increments a PWA badge from the push payload). Computed at send time using
    # the same query as the unread-count endpoint.
    unread_count = Notification.objects.filter(
        recipient_id=user_id, read_at__isnull=True, shown_inapp=True
    ).count()
    payload_dict = {**payload_dict, "unread_count": unread_count}

    subscriptions = PushSubscription.objects.filter(user_id=user_id)
    stale = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload_dict),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                stale.append(sub.pk)
    if stale:
        PushSubscription.objects.filter(pk__in=stale).delete()


@shared_task
def cleanup_old_notifications():
    from datetime import timedelta
    from notifications.models import Notification
    cutoff = timezone.now() - timedelta(hours=24)
    Notification.objects.filter(created_at__lt=cutoff).delete()
