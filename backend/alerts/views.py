import logging

from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as _s
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
from .models import (
    Alert, SEVERITY_ORDER, STATE_NEW, STATE_ACKNOWLEDGED, STATE_IMPORTED, STATE_IGNORED,
    SEVERITY_CHOICES, PAP_CHOICES, TLP_CHOICES,
)
from .serializers import AlertSerializer
from .services.identifiers import next_alert_display_id
from .services.routing import route_alert, _create_incident_from_alert, derive_incident_fields
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

        qs = Alert.objects.select_related("organization", "incident", "acknowledged_by")
        if not request.user.is_staff:
            org = _get_org_for_user(request)
            if org is None:
                return Response({
                    "count": 0, "page": 1, "per_page": 25, "total_pages": 1, "results": []
                })
            qs = qs.filter(organization=org)

        # Apply filters manually
        filterset = AlertFilterSet(request.GET, queryset=qs, request=request)
        if filterset.is_valid():
            qs = filterset.qs

        paginator = AlertPagination()
        paginator.request = request
        page = paginator.paginate_queryset(qs, request)
        ser = AlertSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)

    @extend_schema(
        summary="Ingest alert (staff only)",
        description="Create a new alert for an organisation and run routing. Staff only.",
        request=inline_serializer(
            name="AlertIngestRequest",
            fields={
                "org": _s.CharField(help_text="Organisation slug"),
                "source_kind": _s.ChoiceField(
                    choices=["wazuh_event", "vulnerability", "agent_finding", "api"],
                    help_text="Alert source type",
                ),
                "source_ref": _s.DictField(
                    required=False,
                    allow_null=True,
                    help_text="Source-specific metadata (e.g. agent_name, rule_id)",
                ),
            },
        ),
        responses={201: AlertSerializer},
    )
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

        valid_kinds = {"wazuh_event", "vulnerability", "agent_finding", "api", "workflow", "external"}
        if source_kind not in valid_kinds:
            return Response({"detail": f"source_kind must be one of {sorted(valid_kinds)}."}, status=status.HTTP_400_BAD_REQUEST)

        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Explicit optional enrichment fields
        explicit_title = request.data.get("title") or None
        explicit_severity = request.data.get("severity") or None
        explicit_description = request.data.get("description") or None
        explicit_pap = request.data.get("pap") or None
        explicit_tlp = request.data.get("tlp") or None

        # title is required for workflow/external (no auto-derive fallback exists)
        if source_kind in {"workflow", "external"} and not explicit_title:
            return Response({"detail": "title is required for workflow and external source kinds."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate enum values
        valid_severities = {c[0] for c in SEVERITY_CHOICES}
        if explicit_severity and explicit_severity not in valid_severities:
            return Response({"detail": f"severity must be one of {sorted(valid_severities)}."}, status=status.HTTP_400_BAD_REQUEST)

        valid_pap = {c[0] for c in PAP_CHOICES}
        if explicit_pap and explicit_pap not in valid_pap:
            return Response({"detail": f"pap must be one of {sorted(valid_pap)}."}, status=status.HTTP_400_BAD_REQUEST)

        valid_tlp = {c[0] for c in TLP_CHOICES}
        if explicit_tlp and explicit_tlp not in valid_tlp:
            return Response({"detail": f"tlp must be one of {sorted(valid_tlp)}."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = build_promote_payload(source_kind, source_ref)

        # Explicit fields take precedence; fall back to auto-derived for platform-native kinds
        external_kinds = {"api", "workflow", "external"}
        title = explicit_title or payload["title"]
        # For external kinds, null severity means "not set" — routing/promotion will derive it.
        # For platform-native kinds, always store the auto-derived value so routing thresholds work.
        if explicit_severity:
            severity = explicit_severity
        elif source_kind in external_kinds:
            severity = None
        else:
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
                description=explicit_description,
                pap=explicit_pap,
                tlp=explicit_tlp,
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
        try:
            qs = Alert.objects.select_related("organization", "incident", "acknowledged_by")
            if not request.user.is_staff:
                org = _get_org_for_user(request)
                if org is None:
                    return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
                qs = qs.filter(organization=org)
            return qs.get(display_id=display_id), None
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

        alerts, org, err = _resolve_bulk_promote_alerts(request)
        if err:
            return err

        # Validate and collect optional analyst overrides
        override_severity = request.data.get("severity") or None
        override_pap = request.data.get("pap") or None
        override_tlp = request.data.get("tlp") or None

        if override_severity and override_severity not in {c[0] for c in SEVERITY_CHOICES}:
            return Response({"detail": f"Invalid severity: {override_severity}."}, status=status.HTTP_400_BAD_REQUEST)
        if override_pap and override_pap not in {c[0] for c in PAP_CHOICES}:
            return Response({"detail": f"Invalid pap: {override_pap}."}, status=status.HTTP_400_BAD_REQUEST)
        if override_tlp and override_tlp not in {c[0] for c in TLP_CHOICES}:
            return Response({"detail": f"Invalid tlp: {override_tlp}."}, status=status.HTTP_400_BAD_REQUEST)

        overrides = {
            "title": request.data.get("title") or None,
            "description": request.data.get("description") or None,
            "severity": override_severity,
            "pap": override_pap,
            "tlp": override_tlp,
        }

        lead = max(alerts, key=lambda a: SEVERITY_ORDER.get(a.severity or "info", 0))

        try:
            incident = _create_incident_from_alert(lead, org, overrides=overrides)
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


def _resolve_bulk_promote_alerts(request):
    """
    Shared validation for bulk-promote and preview endpoints.
    Returns (alerts, org, error_response).
    """
    display_ids = request.data.get("alerts", [])
    org_slug = request.data.get("org")

    if not display_ids or not isinstance(display_ids, list):
        return None, None, Response({"detail": "alerts must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

    if not org_slug:
        return None, None, Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        org = Organization.objects.get(slug=org_slug)
    except Organization.DoesNotExist:
        return None, None, Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_staff:
        if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
            return None, None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    alerts = list(
        Alert.objects.filter(display_id__in=display_ids, organization=org).select_related("organization")
    )

    if len(alerts) != len(display_ids):
        return None, None, Response({"detail": "One or more alerts not found."}, status=status.HTTP_404_NOT_FOUND)

    already_imported = [a.display_id for a in alerts if a.state == STATE_IMPORTED]
    if already_imported:
        return None, None, Response(
            {"detail": f"Already-imported alerts cannot be bulk-promoted: {already_imported}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ignored = [a.display_id for a in alerts if a.state == STATE_IGNORED]
    if ignored:
        return None, None, Response(
            {"detail": f"Ignored alerts cannot be bulk-promoted: {ignored}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return alerts, org, None


class AlertBulkPromotePreviewView(APIView):
    """
    POST /api/alerts/bulk-promote/preview/
    Returns the incident fields that would be created by bulk-promote, without writing anything.
    """

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err

        alerts, org, err = _resolve_bulk_promote_alerts(request)
        if err:
            return err

        lead = max(alerts, key=lambda a: SEVERITY_ORDER.get(a.severity or "info", 0))
        fields = derive_incident_fields(lead)

        return Response({
            "title": fields.get("title", ""),
            "description": fields.get("description", ""),
            "severity": fields.get("severity", "medium"),
            "pap": fields.get("pap", "amber"),
            "tlp": fields.get("tlp", "amber"),
        })
