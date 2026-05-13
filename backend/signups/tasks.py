from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone


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
    send_mail(
        subject=f"[vels.online] New signup request: {req.org_name}",
        message=(
            f"A new signup request has been submitted.\n\n"
            f"Name: {req.full_name}\n"
            f"Email: {req.email}\n"
            f"Organisation: {req.org_name}\n"
            f"Intended use:\n{req.intended_use}\n\n"
            f"Review at: {frontend_url}/admin/signup-requests"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=staff_emails,
        fail_silently=True,
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

    send_mail(
        subject="Your invitation to vels.online",
        message=(
            f"Hi {req.full_name},\n\n"
            f"Your signup request for {req.approved_org_name} has been approved.\n\n"
            f"Use the link below to create your account. "
            f"This link expires in 7 days.\n\n"
            f"{invite_url}\n\n"
            f"If you did not request access, please ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[req.email],
        fail_silently=True,
    )


@shared_task
def send_rejection_email_task(signup_request_pk):
    from .models import SignupRequest

    try:
        req = SignupRequest.objects.get(pk=signup_request_pk)
    except SignupRequest.DoesNotExist:
        return

    body = (
        f"Hi {req.full_name},\n\n"
        f"Unfortunately, your signup request for {req.org_name} has not been approved.\n\n"
        f"Reason: {req.rejection_reason}\n"
    )
    if req.rejection_note:
        body += f"\n{req.rejection_note}\n"
    body += "\nYou may resubmit after 24 hours if circumstances change."

    send_mail(
        subject="Your signup request to vels.online",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[req.email],
        fail_silently=True,
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
