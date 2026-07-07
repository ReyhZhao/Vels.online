import datetime

from django.contrib.auth import logout as django_logout
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .serializers import UserSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Ensure csrftoken cookie is written so mutating API calls (POST/PATCH)
        # can include it via X-CSRFToken. API views are @csrf_exempt at the
        # Django middleware level, so without this the cookie is never set.
        # We also return the token in the X-CSRFToken response header so the
        # SPA can set it as a permanent axios default rather than relying on
        # reading document.cookie, which may fail in strict browser contexts.
        csrf_token = get_token(request._request)
        if not request.user.is_authenticated:
            resp = Response(status=status.HTTP_401_UNAUTHORIZED)
            resp['X-CSRFToken'] = csrf_token
            return resp
        resp = Response(UserSerializer(request.user).data)
        resp['X-CSRFToken'] = csrf_token
        return resp

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        default_org_slug = request.data.get("default_org_slug")
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        if default_org_slug is None:
            profile.default_org = None
        else:
            from security.models import Organization
            try:
                if request.user.is_staff:
                    org = Organization.objects.get(slug=default_org_slug)
                else:
                    org = Organization.objects.get(
                        slug=default_org_slug,
                        memberships__user=request.user,
                    )
            except Organization.DoesNotExist:
                return Response({"detail": "Organisation not found."}, status=status.HTTP_400_BAD_REQUEST)
            profile.default_org = org

        profile.save()
        return Response(UserSerializer(request.user).data)


class DashboardOverviewView(APIView):
    """Org-scoped, DB-backed aggregates for the /dashboard page in one round trip.

    Deliberately excludes Wazuh/OpenSearch-derived numbers (agents,
    vulnerabilities, events) — those come from the cached
    ``/api/security/dashboard/`` endpoint, which owns the external calls.
    """

    def get(self, request):
        from incidents.models import Incident
        from alerts.models import Alert
        from ingress.models import Route
        from security.views import _resolve_org

        slug = request.query_params.get("org", "").strip()
        org, err = _resolve_org(request, slug)
        if err:
            return err

        now = timezone.now()
        week_ago = now - datetime.timedelta(days=7)
        day_ago = now - datetime.timedelta(days=1)

        open_states = [
            Incident.STATE_NEW,
            Incident.STATE_TRIAGED,
            Incident.STATE_IN_PROGRESS,
            Incident.STATE_ON_HOLD,
            Incident.STATE_NEEDS_TUNING,
            Incident.STATE_PENDING_CLOSURE,
        ]
        incidents = Incident.objects.filter(organization=org)
        open_incidents = incidents.filter(state__in=open_states)

        by_state = {s: 0 for s in open_states}
        by_state.update(
            {r["state"]: r["n"] for r in open_incidents.values("state").annotate(n=Count("id"))}
        )
        by_severity = {s: 0 for s, _ in Incident.SEVERITY_CHOICES}
        by_severity.update(
            {r["severity"]: r["n"] for r in open_incidents.values("severity").annotate(n=Count("id"))}
        )

        recent = [
            {
                "display_id": i.display_id,
                "title": i.title,
                "severity": i.severity,
                "state": i.state,
                "created_at": i.created_at.isoformat(),
                "assignee": (i.assignee.get_full_name() or i.assignee.username) if i.assignee else None,
            }
            for i in open_incidents.select_related("assignee").order_by("-created_at")[:5]
        ]

        alerts = Alert.objects.filter(organization=org)
        new_alerts = alerts.filter(state="new")
        alert_severity = {s: 0 for s, _ in Alert._meta.get_field("severity").choices}
        unrated = 0
        for r in new_alerts.values("severity").annotate(n=Count("id")):
            if r["severity"]:
                alert_severity[r["severity"]] = r["n"]
            else:
                unrated = r["n"]

        daily = {
            r["day"].isoformat(): r["n"]
            for r in alerts.filter(created_at__gte=week_ago)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(n=Count("id"))
        }
        alert_daily = []
        for offset in range(6, -1, -1):
            d = (now - datetime.timedelta(days=offset)).date().isoformat()
            alert_daily.append({"date": d, "count": daily.get(d, 0)})

        route_status = {s: 0 for s, _ in Route.STATUS_CHOICES}
        route_status.update(
            {
                r["status"]: r["n"]
                for r in Route.objects.filter(organization=org).values("status").annotate(n=Count("id"))
            }
        )

        data = {
            "incidents": {
                "open_total": sum(by_state.values()),
                "by_state": by_state,
                "by_severity": by_severity,
                "created_7d": incidents.filter(created_at__gte=week_ago).count(),
                # No closed_at field exists; updated_at is a fair proxy because
                # resolved/closed incidents are rarely edited afterwards.
                "closed_7d": incidents.filter(
                    state__in=[Incident.STATE_RESOLVED, Incident.STATE_CLOSED],
                    updated_at__gte=week_ago,
                ).count(),
                "recent": recent,
            },
            "alerts": {
                "new_total": new_alerts.count(),
                "last_24h": alerts.filter(created_at__gte=day_ago).count(),
                "by_severity": alert_severity,
                "unrated": unrated,
                "daily_7d": alert_daily,
            },
            "routes": {
                "total": sum(route_status.values()),
                "by_status": route_status,
            },
        }

        if request.user.is_staff:
            data["staff"] = {
                "needs_triage": by_state[Incident.STATE_NEW],
                "pending_closure": by_state[Incident.STATE_PENDING_CLOSURE],
                "unassigned_open": open_incidents.filter(assignee__isnull=True).count(),
            }

        return Response(data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        django_logout(request)
        return Response({"detail": "Logged out."})
