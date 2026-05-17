from datetime import timedelta

from django.utils import timezone

from notifications.models import Notification, NotificationPreferences


def notify(category, recipients, *, incident=None, task=None, payload):
    from notifications.tasks import send_digest_email

    for recipient in recipients:
        if not recipient.is_active:
            continue

        prefs, _ = NotificationPreferences.objects.get_or_create(user=recipient)

        inapp_attr = f"inapp_{category}"
        email_attr = f"email_{category}"

        needs_email = getattr(prefs, email_attr, False)

        # Check before creating whether there's already a pending task for this recipient × incident.
        # If so, don't schedule another — the existing one will batch both notifications.
        has_pending_email_task = False
        if needs_email and incident is not None:
            cutoff = timezone.now() - timedelta(minutes=5)
            has_pending_email_task = Notification.objects.filter(
                recipient=recipient,
                incident=incident,
                email_sent_at__isnull=True,
                created_at__gte=cutoff,
            ).exists()

        needs_inapp = getattr(prefs, inapp_attr, False)

        if needs_inapp or needs_email:
            Notification.objects.create(
                recipient=recipient,
                kind=category,
                incident=incident,
                task=task,
                payload=payload,
                shown_inapp=needs_inapp,
            )

        if needs_email and not has_pending_email_task:
            send_digest_email.apply_async(
                kwargs={
                    "recipient_id": recipient.id,
                    "incident_id": incident.id if incident is not None else None,
                },
                countdown=300,
            )

        push_attr = f"push_{category}"
        needs_push = getattr(prefs, push_attr, False)
        if needs_push:
            from notifications.tasks import send_push_notifications
            send_push_notifications.delay(recipient.id, {
                "title": payload.get("title", "Vels Online"),
                "body": payload.get("body", ""),
                "url": payload.get("link", "/dashboard"),
            })
