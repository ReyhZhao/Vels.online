import logging
from smtplib import SMTPException

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from .email import send_html_email
from .email_defaults import DEFAULT_TEMPLATES
from .models import EmailTemplate, Notification, NotificationPreferences, PushSubscription
from .serializers import EmailTemplateSerializer, NotificationPreferencesSerializer, NotificationSerializer


class NotificationPreferencesView(APIView):
    def get(self, request):
        prefs, _ = NotificationPreferences.objects.get_or_create(user=request.user)
        return Response(NotificationPreferencesSerializer(prefs).data)

    def patch(self, request):
        prefs, _ = NotificationPreferences.objects.get_or_create(user=request.user)
        ser = NotificationPreferencesSerializer(prefs, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        prefs.refresh_from_db()
        return Response(NotificationPreferencesSerializer(prefs).data)


class NotificationListView(APIView):
    PAGE_SIZE = 20

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user, shown_inapp=True).select_related("incident")

        read_filter = request.query_params.get("read")
        if read_filter == "true":
            qs = qs.filter(read_at__isnull=False)
        elif read_filter == "false":
            qs = qs.filter(read_at__isnull=True)

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1

        total = qs.count()
        start = (page - 1) * self.PAGE_SIZE
        results = qs[start: start + self.PAGE_SIZE]

        return Response({
            "count": total,
            "unread_count": Notification.objects.filter(
                recipient=request.user, read_at__isnull=True, shown_inapp=True
            ).count(),
            "page": page,
            "page_size": self.PAGE_SIZE,
            "results": NotificationSerializer(results, many=True).data,
        })


class NotificationReadView(APIView):
    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])

        return Response(NotificationSerializer(notification).data)


class NotificationReadAllView(APIView):
    def post(self, request):
        Notification.objects.filter(
            recipient=request.user, read_at__isnull=True, shown_inapp=True
        ).update(read_at=timezone.now())
        return Response({"detail": "All notifications marked as read."})


class NotificationClearAllView(APIView):
    def delete(self, request):
        deleted, _ = Notification.objects.filter(recipient=request.user).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)


class NotificationDeleteView(APIView):
    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        was_unread = not notification.read_at
        notification.delete()
        return Response({"was_unread": was_unread}, status=status.HTTP_200_OK)


class UnreadCountView(APIView):
    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, read_at__isnull=True, shown_inapp=True
        ).count()
        return Response({"unread_count": count})


class TestEmailView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        recipient = request.user.email
        if not recipient:
            return Response({"detail": "Your account has no email address set."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            send_html_email(
                "test",
                {
                    "recipient_name": request.user.get_full_name() or request.user.username,
                    "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
                },
                [recipient],
            )
        except SMTPException as exc:
            logger.exception("SMTP error sending test email to %s", recipient)
            return Response({"detail": "Failed to send test email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("Unexpected error sending test email to %s", recipient)
            return Response({"detail": "Failed to send test email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"detail": f"Test email sent to {recipient}."})


class TestPushView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        if not PushSubscription.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "No push subscriptions found. Enable push notifications first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .tasks import send_push_notifications
        send_push_notifications.delay(request.user.id, {
            "title": "Test Push Notification",
            "body": "Push notifications are working correctly.",
            "url": "/account/notifications",
        })
        return Response({"detail": "Test push notification sent."})


class PushVapidKeyView(APIView):
    def get(self, request):
        return Response({"public_key": settings.VAPID_PUBLIC_KEY})


class PushSubscribeView(APIView):
    def post(self, request):
        endpoint = request.data.get("endpoint", "")
        p256dh = request.data.get("p256dh", "")
        auth_key = request.data.get("auth", "")
        if not endpoint:
            return Response({"detail": "endpoint is required."}, status=status.HTTP_400_BAD_REQUEST)
        _, created = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": request.user, "p256dh": p256dh, "auth": auth_key},
        )
        return Response(status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        endpoint = request.data.get("endpoint", "")
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailTemplateListView(APIView):
    """List all known email templates (DB record or built-in default)."""

    def get(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)

        db_records = {t.name: t for t in EmailTemplate.objects.all()}
        results = []
        for name, defaults in DEFAULT_TEMPLATES.items():
            if name in db_records:
                results.append(EmailTemplateSerializer(db_records[name]).data)
            else:
                results.append({
                    "name": name,
                    "subject": defaults["subject"],
                    "html_body": defaults["html_body"],
                    "description": defaults["description"],
                    "updated_at": None,
                })
        return Response(results)


class EmailTemplateDetailView(APIView):
    """Get or update a single email template."""

    def _get_or_default(self, name):
        if name not in DEFAULT_TEMPLATES:
            return None, None
        try:
            return EmailTemplate.objects.get(name=name), True
        except EmailTemplate.DoesNotExist:
            defaults = DEFAULT_TEMPLATES[name]
            return EmailTemplate(
                name=name,
                subject=defaults["subject"],
                html_body=defaults["html_body"],
                description=defaults["description"],
            ), False

    def get(self, request, name):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        tmpl, in_db = self._get_or_default(name)
        if tmpl is None:
            return Response({"detail": "Unknown template."}, status=status.HTTP_404_NOT_FOUND)
        data = EmailTemplateSerializer(tmpl).data
        data["in_db"] = in_db
        return Response(data)

    def put(self, request, name):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if name not in DEFAULT_TEMPLATES:
            return Response({"detail": "Unknown template."}, status=status.HTTP_404_NOT_FOUND)

        tmpl, _ = EmailTemplate.objects.get_or_create(
            name=name,
            defaults={
                "subject": DEFAULT_TEMPLATES[name]["subject"],
                "html_body": DEFAULT_TEMPLATES[name]["html_body"],
                "description": DEFAULT_TEMPLATES[name]["description"],
            },
        )
        ser = EmailTemplateSerializer(tmpl, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        return Response(ser.data)

    def delete(self, request, name):
        """Reset a template back to the built-in default by deleting the DB override."""
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            EmailTemplate.objects.get(name=name).delete()
        except EmailTemplate.DoesNotExist:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)
