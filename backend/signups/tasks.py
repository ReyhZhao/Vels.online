from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from notifications.email import send_html_email


@shared_task
def send_admin_notification_email(signup_request_pk):
    from .models import SignupRequest

    try:
        req = SignupRequest.objects.get(pk=signup_request_pk)
    except SignupRequest.DoesNotExist:
        return

    User = get_user_model()
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not staff_emails:
        return

    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    send_html_email(
        "signup_request",
        {
            "full_name": req.full_name,
            "email": req.email,
            "org_name": req.org_name,
            "intended_use": req.intended_use,
            "review_url": f"{frontend_url}/admin/signup-requests",
            "frontend_url": frontend_url,
        },
        staff_emails,
    )


@shared_task
def send_invite_email(signup_request_pk):
    from .authentik import AuthentikClient
    from .models import SignupRequest

    try:
        req = SignupRequest.objects.get(pk=signup_request_pk)
    except SignupRequest.DoesNotExist:
        return

    flow_slug = getattr(settings, "AUTHENTIK_ENROLLMENT_FLOW_SLUG", "")
    invite_url = AuthentikClient().build_invite_url(flow_slug, str(req.invite_token))

    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    send_html_email(
        "invite",
        {
            "full_name": req.full_name,
            "org_name": req.approved_org_name,
            "invite_url": invite_url,
            "frontend_url": frontend_url,
        },
        [req.email],
    )


@shared_task
def send_rejection_email_task(signup_request_pk):
    from .models import SignupRequest

    try:
        req = SignupRequest.objects.get(pk=signup_request_pk)
    except SignupRequest.DoesNotExist:
        return

    frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    send_html_email(
        "rejection",
        {
            "full_name": req.full_name,
            "org_name": req.org_name,
            "rejection_reason": req.rejection_reason,
            "rejection_note": req.rejection_note or "",
            "frontend_url": frontend_url,
        },
        [req.email],
    )


@shared_task
def expire_stale_invites():
    from .models import SignupRequest

    now = timezone.now()
    expired = SignupRequest.objects.filter(
        status=SignupRequest.STATUS_APPROVED,
        invite_expires_at__lt=now,
    ).update(status=SignupRequest.STATUS_EXPIRED)
    return expired
