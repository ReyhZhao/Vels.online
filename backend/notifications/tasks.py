from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone


@shared_task
def send_digest_email(recipient_id, incident_id):
    try:
        recipient = User.objects.get(pk=recipient_id)
    except User.DoesNotExist:
        return

    from notifications.models import Notification

    qs = Notification.objects.filter(recipient=recipient, email_sent_at__isnull=True)
    if incident_id is not None:
        qs = qs.filter(incident_id=incident_id)

    notifications = list(qs.select_related("incident").order_by("created_at"))
    if not notifications:
        return

    lines = []
    for n in notifications:
        title = n.payload.get("title", f"Notification: {n.kind}")
        body = n.payload.get("body", "")
        link = n.payload.get("link", "")
        lines.append(f"• {title}")
        if body:
            lines.append(f"  {body}")
        if link:
            lines.append(f"  {link}")

    send_mail(
        subject=f"Vels Online: {len(notifications)} notification(s) for you",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient.email],
        fail_silently=True,
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
