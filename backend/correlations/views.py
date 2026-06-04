import logging

from rest_framework import serializers as _s
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .models import DetectionSuggestion
from .tasks import _create_incident_from_suggestion

logger = logging.getLogger(__name__)


class _AlertBriefSerializer(_s.Serializer):
    id = _s.IntegerField()
    display_id = _s.CharField()
    title = _s.CharField()
    severity = _s.CharField()


class _DetectionSuggestionSerializer(_s.ModelSerializer):
    proposed_alerts = _AlertBriefSerializer(many=True, read_only=True)
    incident_display_id = _s.SerializerMethodField()

    class Meta:
        model = DetectionSuggestion
        fields = [
            "id",
            "organization",
            "proposed_alerts",
            "rationale",
            "confidence",
            "status",
            "incident",
            "incident_display_id",
            "created_at",
            "updated_at",
        ]

    def get_incident_display_id(self, obj):
        return obj.incident.display_id if obj.incident_id else None


def _get_org_for_user(request):
    """Return (org, error_response) from ?org=<slug> query param, checking membership."""
    if not request.user.is_authenticated:
        return None, Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

    org_slug = request.query_params.get("org") or request.data.get("org")
    if not org_slug:
        return None, Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        org = Organization.objects.get(slug=org_slug)
    except Organization.DoesNotExist:
        return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_staff:
        if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
            return None, Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

    return org, None


class DetectionSuggestionListView(APIView):
    def get(self, request):
        org, err = _get_org_for_user(request)
        if err:
            return err

        status_filter = request.query_params.get("status", DetectionSuggestion.STATUS_PENDING)
        qs = (
            DetectionSuggestion.objects
            .filter(organization=org, status=status_filter)
            .prefetch_related("proposed_alerts")
            .select_related("incident")
        )
        return Response(_DetectionSuggestionSerializer(qs, many=True).data)


class DetectionSuggestionAcceptView(APIView):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        try:
            suggestion = DetectionSuggestion.objects.select_related("organization", "incident").prefetch_related("proposed_alerts").get(pk=pk)
        except DetectionSuggestion.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(
                user=request.user, organization=suggestion.organization
            ).exists():
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if suggestion.status != DetectionSuggestion.STATUS_PENDING:
            return Response(
                {"detail": f"Suggestion is already {suggestion.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            incident = _create_incident_from_suggestion(suggestion)
        except Exception:
            logger.exception("DetectionSuggestionAcceptView: failed for suggestion %s", pk)
            return Response({"detail": "Failed to create incident."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        suggestion.refresh_from_db()
        return Response(
            {
                "suggestion": _DetectionSuggestionSerializer(suggestion).data,
                "incident_display_id": incident.display_id if incident else None,
            },
            status=status.HTTP_200_OK,
        )


class DetectionSuggestionDismissView(APIView):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        try:
            suggestion = DetectionSuggestion.objects.select_related("organization").get(pk=pk)
        except DetectionSuggestion.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(
                user=request.user, organization=suggestion.organization
            ).exists():
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if suggestion.status != DetectionSuggestion.STATUS_PENDING:
            return Response(
                {"detail": f"Suggestion is already {suggestion.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.status = DetectionSuggestion.STATUS_DISMISSED
        suggestion.save(update_fields=["status", "updated_at"])

        return Response(_DetectionSuggestionSerializer(suggestion).data)
