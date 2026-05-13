from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from security.models import Organization

from .authentik import AuthentikClient, AuthentikAPIError
from .models import InvalidTransition, SignupRequest
from .serializers import (
    ApproveSerializer,
    RejectSerializer,
    SignupRequestSerializer,
    SignupSubmitSerializer,
)
from .tasks import send_admin_notification_email, send_invite_email, send_rejection_email_task
from .turnstile import verify_turnstile

INVITE_TTL_DAYS = 7


class SignupThrottle(AnonRateThrottle):
    rate = "3/hour"


class SignupRequestListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAdminUser()]

    def get_throttles(self):
        if self.request.method == "POST":
            return [SignupThrottle()]
        return []

    def get(self, request):
        qs = SignupRequest.objects.all()
        status_filter = request.query_params.get("status", "")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(SignupRequestSerializer(qs, many=True).data)

    def post(self, request):
        ser = SignupSubmitSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        # Honeypot — silently succeed without creating a record
        if ser.validated_data.get("website"):
            return Response({"detail": "Thank you for your submission."})

        # Turnstile verification
        remote_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or None
        )
        try:
            verify_turnstile(ser.validated_data["cf_turnstile_response"], remote_ip)
        except Exception:
            return Response(
                {"detail": "Bot protection check failed. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = ser.validated_data["email"].lower()

        # Duplicate detection: pending or approved → generic 200 (no email enumeration)
        if SignupRequest.objects.filter(
            email=email, status__in=[SignupRequest.STATUS_PENDING, SignupRequest.STATUS_APPROVED]
        ).exists():
            return Response(
                {"detail": "We already have your details. Check your inbox for updates."}
            )

        # Rejected cooldown: 24 hours
        cooldown_cutoff = timezone.now() - timedelta(hours=24)
        if SignupRequest.objects.filter(
            email=email,
            status=SignupRequest.STATUS_REJECTED,
            actioned_at__gte=cooldown_cutoff,
        ).exists():
            return Response(
                {"detail": "Please wait 24 hours before resubmitting."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        req = SignupRequest.objects.create(
            email=email,
            full_name=ser.validated_data["full_name"],
            org_name=ser.validated_data["org_name"],
            intended_use=ser.validated_data["intended_use"],
        )

        send_admin_notification_email.delay(req.pk)
        return Response({"detail": "Thank you for your submission. We'll be in touch soon."})


class SignupRequestPendingCountView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        count = SignupRequest.objects.filter(status=SignupRequest.STATUS_PENDING).count()
        return Response({"count": count})


class SignupRequestDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        try:
            return SignupRequest.objects.get(pk=pk), None
        except SignupRequest.DoesNotExist:
            return None, Response(status=status.HTTP_404_NOT_FOUND)

    def get(self, request, pk):
        req, err = self._get(pk)
        if err:
            return err
        return Response(SignupRequestSerializer(req).data)

    def delete(self, request, pk):
        req, err = self._get(pk)
        if err:
            return err

        client = AuthentikClient()
        if req.authentik_group_pk:
            try:
                client.delete_group(req.authentik_group_pk)
            except AuthentikAPIError:
                pass
        if req.invite_token:
            try:
                client.delete_invitation(str(req.invite_token))
            except AuthentikAPIError:
                pass

        if req.org_slug:
            Organization.objects.filter(slug=req.org_slug).delete()

        req.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _provision_and_approve(req, org_name_override=None):
    """
    Creates Authentik group + invite, Django Organisation, and marks the request approved.
    Returns (updated_req, error_response_or_None).
    """
    org_name = org_name_override or req.org_name
    org_slug = slugify(org_name)

    if Organization.objects.filter(slug=org_slug).exists() and req.org_slug != org_slug:
        return None, Response(
            {
                "detail": (
                    "An organisation with this name already exists. "
                    "Provide approved_org_name to use a different name."
                ),
                "conflict": True,
            },
            status=status.HTTP_409_CONFLICT,
        )

    client = AuthentikClient()
    flow_slug = getattr(settings, "AUTHENTIK_ENROLLMENT_FLOW_SLUG", "")

    # Create Authentik group if not already provisioned
    group_pk = req.authentik_group_pk
    if not group_pk:
        try:
            group_pk = client.create_group(f"customer:{org_slug}")
        except AuthentikAPIError as exc:
            return None, Response(
                {"detail": f"Failed to create Authentik group: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # Delete stale invitation before creating a new one (resend path)
    if req.invite_token:
        try:
            client.delete_invitation(str(req.invite_token))
        except AuthentikAPIError:
            pass

    # expiry is set by the model's approve()/resend() method, pass a placeholder datetime
    # for the Authentik API call — the model computes the real expiry
    placeholder_expires = timezone.now() + timedelta(days=7)
    try:
        invitation = client.create_invitation(flow_slug, placeholder_expires)
    except AuthentikAPIError as exc:
        return None, Response(
            {"detail": f"Failed to create Authentik invitation: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # Ensure the Django Organisation exists
    if req.org_slug != org_slug:
        Organization.objects.get_or_create(
            slug=org_slug,
            defaults={"name": org_name, "wazuh_group": org_slug},
        )

    # Drive state via model transition method
    if req.status == SignupRequest.STATUS_PENDING:
        req.approve(org_name, org_slug, group_pk, invitation["token"])
    else:
        req.resend(invitation["token"])
    req.save()

    send_invite_email.delay(req.pk)
    return req, None


class SignupRequestApproveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            req = SignupRequest.objects.get(pk=pk)
        except SignupRequest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if req.status != SignupRequest.STATUS_PENDING:
            return Response(
                {"detail": "Only pending requests can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = ApproveSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        req, err = _provision_and_approve(req, ser.validated_data.get("approved_org_name") or None)
        if err:
            return err
        return Response(SignupRequestSerializer(req).data)


class SignupRequestRejectView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            req = SignupRequest.objects.get(pk=pk)
        except SignupRequest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        ser = RejectSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            req.reject(
                reason=ser.validated_data["rejection_reason"],
                note=ser.validated_data.get("rejection_note", ""),
                send_email=ser.validated_data.get("send_rejection_email", True),
            )
        except InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        req.save()

        if req.send_rejection_email:
            send_rejection_email_task.delay(req.pk)

        return Response(SignupRequestSerializer(req).data)


class SignupRequestResendView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            req = SignupRequest.objects.get(pk=pk)
        except SignupRequest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if req.status != SignupRequest.STATUS_EXPIRED:
            return Response(
                {"detail": "Only expired requests can have their invite resent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        req, err = _provision_and_approve(req, req.approved_org_name or None)
        if err:
            return err
        return Response(SignupRequestSerializer(req).data)
