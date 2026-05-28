import logging

from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent
from incidents.services.events import record_event
from incidents.services.promote import build_promote_payload

from .filters import AlertFilterSet
from .models import Alert, SEVERITY_ORDER, STATE_NEW, STATE_ACKNOWLEDGED, STATE_IMPORTED, STATE_IGNORED
from .serializers import AlertSerializer
from .services.identifiers import next_alert_display_id
from .services.routing import route_alert, _create_incident_from_alert
from .services.side_effects import apply_link_side_effects

logger = logging.getLogger(__name__)

SEVERITY_RANK = ["info", "low", "medium", "high", "critical"]

# Valid manual state transitions
VALID_TRANSITIONS = {
    STATE_NEW: {STATE_ACKNOWLEDGED, STATE_IGNORED},
    STATE_ACKNOWLEDGED: {STATE_IGNORED},
}


def _require_auth(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    return None


def _get_org_for_user(request):
    membership = (
        OrganizationMembership.objects.filter(user=request.user)
        .select_related("organization")
        .first()
    )
    return membership.organization if membership else None


class AlertPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "per_page"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "page": self.page.number,
            "per_page": self.get_page_size(self.request),
            "total_pages": self.page.paginator.num_pages,
            "results": data,
        })


class AlertListIngestView(APIView):
    """
    GET  /api/alerts/  — paginated alert list scoped to user's org
    POST /api/alerts/  — staff-only ingest endpoint
    """

    def get(self, request):
        err = _require_auth(request)
        if err:
            return err

        org = _get_org_for_user(request)
        if org is None:
            return Response({
                "count": 0, "page": 1, "per_page": 25, "total_pages": 1, "results": []
            })

        qs = Alert.objects.filter(organization=org).select_related(
            "organization", "incident", "acknowledged_by"
        )

        # Apply filters manually
        filterset = AlertFilterSet(request.GET, queryset=qs, request=request)
        if filterset.is_valid():
            qs = filterset.qs

        paginator = AlertPagination()
        paginator.request = request
        page = paginator.paginate_queryset(qs, request)
        ser = AlertSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        source_kind = request.data.get("source_kind")
        source_ref = request.data.get("source_ref") or {}
        org_slug = request.data.get("org")

        if not source_kind:
            return Response({"detail": "source_kind is required."}, status=status.HTTP_400_BAD_REQUEST)

        valid_kinds = {"wazuh_event", "vulnerability", "agent_finding", "api"}
        if source_kind not in valid_kinds:
            return Response({"detail": f"source_kind must be one of {sorted(valid_kinds)}."}, status=status.HTTP_400_BAD_REQUEST)

        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_promote_payload(source_kind, source_ref)
        title = payload["title"]
        severity = payload["severity"]

        with transaction.atomic():
            display_id = next_alert_display_id()
            alert = Alert.objects.create(
                organization=org,
                display_id=display_id,
                source_kind=source_kind,
                source_ref=source_ref,
                title=title,
                severity=severity,
                state=STATE_NEW,
            )

        try:
            route_alert(alert)
        except Exception:
            logger.exception("route_alert failed for alert %s", alert.display_id)

        alert.refresh_from_db()
        return Response(AlertSerializer(alert).data, status=status.HTTP_201_CREATED)


class AlertDetailView(APIView):
    """
    GET   /api/alerts/<display_id>/  — retrieve a single alert
    PATCH /api/alerts/<display_id>/  — state transitions + re-link
    """

    def _get_alert(self, request, display_id):
        org = _get_org_for_user(request)
        if org is None:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Alert.objects.select_related(
                "organization", "incident", "acknowledged_by"
            ).get(display_id=display_id, organization=org), None
        except Alert.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request, display_id):
        err = _require_auth(request)
        if err:
            return err
        alert, err = self._get_alert(request, display_id)
        if err:
            return err
        return Response(AlertSerializer(alert).data)

    def patch(self, request, display_id):
        err = _require_auth(request)
        if err:
            return err
        alert, err = self._get_alert(request, display_id)
        if err:
            return err

        new_state = request.data.get("state")
        new_incident_ref = request.data.get("incident")

        # Handle state transition
        if new_state is not None:
            return self._handle_state_transition(request, alert, new_state)

        # Handle incident re-link
        if new_incident_ref is not None:
            return self._handle_relink(request, alert, new_incident_ref)

        return Response({"detail": "Provide 'state' or 'incident' to patch."}, status=status.HTTP_400_BAD_REQUEST)

    def _handle_state_transition(self, request, alert, new_state):
        valid_targets = VALID_TRANSITIONS.get(alert.state, set())
        if new_state not in valid_targets:
            return Response(
                {"detail": f"Cannot transition from '{alert.state}' to '{new_state}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_fields = ["state", "updated_at"]
        alert.state = new_state

        if new_state == STATE_ACKNOWLEDGED:
            alert.acknowledged_by = request.user
            alert.acknowledged_at = timezone.now()
            update_fields += ["acknowledged_by", "acknowledged_at"]

        alert.save(update_fields=update_fields)
        return Response(AlertSerializer(alert).data)

    def _handle_relink(self, request, alert, incident_ref):
        if alert.state != STATE_IMPORTED:
            return Response(
                {"detail": "Only imported alerts can be re-linked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = alert.organization
        try:
            new_incident = Incident.objects.get(display_id=incident_ref, organization=org)
        except Incident.DoesNotExist:
            return Response({"detail": "Target incident not found."}, status=status.HTTP_400_BAD_REQUEST)

        if alert.incident_id and alert.incident_id == new_incident.id:
            return Response(AlertSerializer(alert).data)

        old_incident = alert.incident

        with transaction.atomic():
            alert.incident = new_incident
            alert.save(update_fields=["incident", "updated_at"])

            # Side effects on new incident
            apply_link_side_effects(alert, new_incident)

            # Record event on old incident noting the alert was re-routed away
            if old_incident:
                record_event(
                    old_incident,
                    "alert_relinked",
                    payload={
                        "alert_display_id": alert.display_id,
                        "new_incident_display_id": new_incident.display_id,
                    },
                )

        alert.refresh_from_db()
        return Response(AlertSerializer(alert).data)


class AlertBulkPromoteView(APIView):
    """
    POST /api/alerts/bulk-promote/
    Body: { "alerts": ["AL-001", "AL-005"], "org": "acme" }
    All alerts must be in state 'new' or 'acknowledged'.
    Creates one incident from the highest-severity alert.
    """

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err

        display_ids = request.data.get("alerts", [])
        org_slug = request.data.get("org")

        if not display_ids or not isinstance(display_ids, list):
            return Response({"detail": "alerts must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            # Non-staff: verify user belongs to org
            if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        alerts = list(
            Alert.objects.filter(
                display_id__in=display_ids,
                organization=org,
            ).select_related("organization")
        )

        if len(alerts) != len(display_ids):
            # Some alerts not found or belong to different org
            return Response({"detail": "One or more alerts not found."}, status=status.HTTP_404_NOT_FOUND)

        already_imported = [a.display_id for a in alerts if a.state == STATE_IMPORTED]
        if already_imported:
            return Response(
                {"detail": f"Already-imported alerts cannot be bulk-promoted: {already_imported}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ignored = [a.display_id for a in alerts if a.state == STATE_IGNORED]
        if ignored:
            return Response(
                {"detail": f"Ignored alerts cannot be bulk-promoted: {ignored}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Derive title/severity from the highest-severity alert in the selection
        lead = max(alerts, key=lambda a: SEVERITY_ORDER.get(a.severity, 0))

        try:
            incident = _create_incident_from_alert(lead, org)
        except Exception:
            logger.exception("bulk-promote: failed to create incident")
            return Response({"detail": "Failed to create incident."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        with transaction.atomic():
            for a in alerts:
                a.state = STATE_IMPORTED
                a.incident = incident
                a.save(update_fields=["state", "incident", "updated_at"])
                apply_link_side_effects(a, incident)

        from incidents.serializers import IncidentSerializer
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)
