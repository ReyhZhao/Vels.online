from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreferences
from .serializers import NotificationPreferencesSerializer, NotificationSerializer


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
            send_mail(
                subject="[vels.online] Test email",
                message="This is a test email sent from the vels.online admin dashboard to verify email delivery.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except SMTPException as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"detail": f"Test email sent to {recipient}."})
