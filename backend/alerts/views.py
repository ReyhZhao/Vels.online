import logging

from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
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
    Alert, AlertEntity, SEVERITY_ORDER, STATE_NEW, STATE_ACKNOWLEDGED, STATE_IMPORTED, STATE_IGNORED,
    SEVERITY_CHOICES, PAP_CHOICES, TLP_CHOICES,
)
from .serializers import AlertSerializer
from .services.entities import entities_for
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

    @extend_schema(
        summary="List alerts",
        description="Returns a paginated list of alerts scoped to the authenticated user's organisation. Staff users see all alerts.",
        parameters=[
            OpenApiParameter("state", OpenApiTypes.STR, description="Filter by state: new | acknowledged | imported | ignored"),
            OpenApiParameter("severity", OpenApiTypes.STR, description="Filter by severity: critical | high | medium | low | info"),
            OpenApiParameter("source_kind", OpenApiTypes.STR, description="Filter by source: wazuh_event | vulnerability | agent_finding | api | workflow | external | inbound_email"),
            OpenApiParameter("date_from", OpenApiTypes.DATE, description="Created on or after this date (YYYY-MM-DD)"),
            OpenApiParameter("date_to", OpenApiTypes.DATE, description="Created on or before this date (YYYY-MM-DD)"),
            OpenApiParameter("exclude_state", OpenApiTypes.STR, description="Comma-separated states to exclude, e.g. closed,ignored"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number (default: 1)"),
            OpenApiParameter("per_page", OpenApiTypes.INT, description="Page size (default: 25, max: 100)"),
        ],
        responses={200: AlertSerializer(many=True)},
    )
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
        description=(
            "Create a new alert for an organisation and run routing. Staff only.\n\n"
            "**Enrichment fields** (`title`, `description`, `severity`, `pap`, `tlp`) are optional "
            "for platform-native source kinds (`wazuh_event`, `vulnerability`, `agent_finding`) — "
            "values are auto-derived from `source_ref` when omitted. "
            "For `workflow` and `external` source kinds `title` is required and severity/pap/tlp "
            "remain `null` unless explicitly supplied."
        ),
        request=inline_serializer(
            name="AlertIngestRequest",
            fields={
                "org": _s.CharField(help_text="Organisation slug"),
                "source_kind": _s.ChoiceField(
                    choices=["wazuh_event", "vulnerability", "agent_finding", "api", "workflow", "external"],
                    help_text="Alert source type",
                ),
                "source_ref": _s.DictField(
                    required=False,
                    allow_null=True,
                    help_text="Source-specific metadata (e.g. agent_name, rule_id)",
                ),
                "title": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Human-readable title. Required for workflow/external; overrides auto-derived value for other kinds.",
                ),
                "description": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Free-text description of the alert. Stored as-is; not auto-derived.",
                ),
                "severity": _s.ChoiceField(
                    choices=["critical", "high", "medium", "low", "info"],
                    required=False,
                    allow_null=True,
                    help_text="Severity override. For workflow/external kinds, omitting this stores null.",
                ),
                "pap": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="PAP classification override.",
                ),
                "tlp": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="TLP classification override.",
                ),
                "entities": _s.DictField(
                    required=False,
                    allow_null=True,
                    help_text=(
                        "Optional ECS entity envelope. Keys must be ECS field names "
                        "(host.name, source.ip, user.name, file.hash.sha256, process.name). "
                        "Values are canonicalised on ingest. Unknown keys are ignored."
                    ),
                ),
            },
        ),
        responses={
            201: AlertSerializer,
            400: inline_serializer(name="AlertIngestError", fields={"detail": _s.CharField()}),
            403: inline_serializer(name="AlertIngestForbidden", fields={"detail": _s.CharField()}),
            404: inline_serializer(name="AlertIngestNotFound", fields={"detail": _s.CharField()}),
        },
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
        entities_envelope = request.data.get("entities") or None

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
            _save_alert_entities(alert, org, entities_envelope)

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

    @extend_schema(
        summary="Retrieve alert",
        description="Returns the full detail of a single alert by its display ID.",
        responses={
            200: AlertSerializer,
            404: inline_serializer(name="AlertDetailNotFound", fields={"detail": _s.CharField()}),
        },
    )
    def get(self, request, display_id):
        err = _require_auth(request)
        if err:
            return err
        alert, err = self._get_alert(request, display_id)
        if err:
            return err
        return Response(AlertSerializer(alert).data)

    @extend_schema(
        summary="Update alert state or incident link",
        description=(
            "Performs one of two mutually exclusive operations:\n\n"
            "- **State transition** (`state` field): moves the alert through its lifecycle. "
            "Valid transitions: `new` → `acknowledged` or `ignored`; `acknowledged` → `ignored`.\n"
            "- **Incident re-link** (`incident` field): reassigns the alert to a different incident. "
            "Only allowed when the alert is in `imported` state."
        ),
        request=inline_serializer(
            name="AlertPatchRequest",
            fields={
                "state": _s.ChoiceField(
                    choices=["acknowledged", "ignored"],
                    required=False,
                    help_text="Target state for the transition.",
                ),
                "incident": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Display ID of the target incident (re-link; only for imported alerts).",
                ),
            },
        ),
        responses={
            200: AlertSerializer,
            400: inline_serializer(name="AlertPatchError", fields={"detail": _s.CharField()}),
            404: inline_serializer(name="AlertPatchNotFound", fields={"detail": _s.CharField()}),
        },
    )
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

    @extend_schema(
        summary="Bulk-promote alerts to an incident",
        description=(
            "Creates a single incident from one or more alerts and marks all of them as `imported`. "
            "The incident fields are derived from the highest-severity alert in the selection. "
            "Any of the five incident fields can be overridden by including them in the request body — "
            "call `POST /api/alerts/bulk-promote/preview/` first to get the auto-derived defaults.\n\n"
            "All supplied alerts must belong to the given organisation and must not already be in "
            "`imported` or `ignored` state."
        ),
        request=inline_serializer(
            name="AlertBulkPromoteRequest",
            fields={
                "alerts": _s.ListField(
                    child=_s.CharField(),
                    help_text="List of alert display IDs to promote (e.g. ['AL-001', 'AL-005']).",
                ),
                "org": _s.CharField(help_text="Organisation slug that owns the alerts."),
                "title": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Incident title override. Defaults to the auto-derived value.",
                ),
                "description": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Incident description override.",
                ),
                "severity": _s.ChoiceField(
                    choices=["critical", "high", "medium", "low", "info"],
                    required=False,
                    allow_null=True,
                    help_text="Severity override. Defaults to the highest severity across selected alerts.",
                ),
                "pap": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="PAP classification override.",
                ),
                "tlp": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="TLP classification override.",
                ),
            },
        ),
        responses={
            201: inline_serializer(
                name="AlertBulkPromoteResponse",
                fields={"display_id": _s.CharField(help_text="Display ID of the newly created incident.")},
            ),
            400: inline_serializer(name="AlertBulkPromoteError", fields={"detail": _s.CharField()}),
            404: inline_serializer(name="AlertBulkPromoteNotFound", fields={"detail": _s.CharField()}),
        },
    )
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

    @extend_schema(
        summary="Preview bulk-promote incident fields",
        description=(
            "Dry-run companion to `POST /api/alerts/bulk-promote/`. "
            "Returns the five incident fields (`title`, `description`, `severity`, `pap`, `tlp`) "
            "that would be derived from the selected alerts without creating anything. "
            "Use this to pre-populate a confirmation dialog before calling the promote endpoint."
        ),
        request=inline_serializer(
            name="AlertBulkPromotePreviewRequest",
            fields={
                "alerts": _s.ListField(
                    child=_s.CharField(),
                    help_text="List of alert display IDs to preview (e.g. ['AL-001', 'AL-005']).",
                ),
                "org": _s.CharField(help_text="Organisation slug that owns the alerts."),
            },
        ),
        responses={
            200: inline_serializer(
                name="AlertBulkPromotePreviewResponse",
                fields={
                    "title": _s.CharField(help_text="Derived incident title."),
                    "description": _s.CharField(help_text="Derived incident description."),
                    "severity": _s.ChoiceField(
                        choices=["critical", "high", "medium", "low", "info"],
                        help_text="Derived severity (highest across selected alerts).",
                    ),
                    "pap": _s.ChoiceField(
                        choices=["white", "green", "amber", "red"],
                        help_text="Derived PAP classification.",
                    ),
                    "tlp": _s.ChoiceField(
                        choices=["white", "green", "amber", "red"],
                        help_text="Derived TLP classification.",
                    ),
                },
            ),
            400: inline_serializer(name="AlertBulkPreviewError", fields={"detail": _s.CharField()}),
            404: inline_serializer(name="AlertBulkPreviewNotFound", fields={"detail": _s.CharField()}),
        },
    )
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


def _save_alert_entities(alert, org, envelope):
    """Persist AlertEntity rows for the given envelope dict. No-op when envelope is falsy."""
    if not envelope:
        return
    for entity_type, value in entities_for({"entities": envelope}):
        AlertEntity.objects.create(
            alert=alert,
            organization=org,
            entity_type=entity_type,
            value=value,
        )


_ENTITY_ENVELOPE_DETAIL = (
    "entities must be an object containing at least one recognised ECS field "
    "(host.name, source.ip, user.name, file.hash.sha256, process.name) "
    "with a non-empty string value."
)


class AlertListIngestV2View(AlertListIngestView):
    """
    POST /api/v2/alerts/ — entity-envelope-required ingest endpoint.

    Identical to v1 but rejects requests whose ``entities`` field is absent,
    not an object, or contains no recognised ECS field with a non-empty value.
    Existing callers of /api/alerts/ continue to work; new integrators should
    target this endpoint.
    """

    @extend_schema(
        summary="Ingest alert — v2 (entity envelope required)",
        description=(
            "Create a new alert. Identical to `POST /api/alerts/` (v1) except the "
            "`entities` ECS envelope is **required**. Requests without a valid envelope "
            "are rejected with HTTP 422.\n\n"
            "**Required envelope fields** (at least one must be present with a non-empty value):\n"
            "- `host.name` — fully-qualified hostname\n"
            "- `source.ip` — IPv4/IPv6 address of the traffic source\n"
            "- `user.name` — account name (DOMAIN\\user, user@domain, and bare forms are all normalised)\n"
            "- `file.hash.sha256` — 64-character hex SHA-256 digest\n"
            "- `process.name` — process image name\n\n"
            "Values are canonicalised (lowercased, domain prefix stripped) on ingest."
        ),
        request=inline_serializer(
            name="AlertIngestV2Request",
            fields={
                "org": _s.CharField(help_text="Organisation slug"),
                "source_kind": _s.ChoiceField(
                    choices=["wazuh_event", "vulnerability", "agent_finding", "api", "workflow", "external"],
                    help_text="Alert source type",
                ),
                "source_ref": _s.DictField(
                    required=False,
                    allow_null=True,
                    help_text="Source-specific metadata (e.g. agent_name, rule_id)",
                ),
                "title": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Human-readable title. Required for workflow/external.",
                ),
                "description": _s.CharField(
                    required=False,
                    allow_null=True,
                    help_text="Free-text description.",
                ),
                "severity": _s.ChoiceField(
                    choices=["critical", "high", "medium", "low", "info"],
                    required=False,
                    allow_null=True,
                    help_text="Severity override.",
                ),
                "pap": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="PAP classification override.",
                ),
                "tlp": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    allow_null=True,
                    help_text="TLP classification override.",
                ),
                "entities": _s.DictField(
                    help_text=(
                        "**Required.** ECS entity envelope. Keys must be ECS field names "
                        "(host.name, source.ip, user.name, file.hash.sha256, process.name). "
                        "At least one key must have a non-empty string value."
                    ),
                ),
            },
        ),
        responses={
            201: AlertSerializer,
            400: inline_serializer(name="AlertIngestV2Error", fields={"detail": _s.CharField()}),
            403: inline_serializer(name="AlertIngestV2Forbidden", fields={"detail": _s.CharField()}),
            404: inline_serializer(name="AlertIngestV2NotFound", fields={"detail": _s.CharField()}),
            422: inline_serializer(name="AlertIngestV2EnvelopeError", fields={"detail": _s.CharField()}),
        },
    )
    def post(self, request):
        envelope = request.data.get("entities")
        if not envelope or not isinstance(envelope, dict):
            return Response(
                {"detail": "entities is required. " + _ENTITY_ENVELOPE_DETAIL},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not entities_for({"entities": envelope}):
            return Response(
                {"detail": _ENTITY_ENVELOPE_DETAIL},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return super().post(request)
