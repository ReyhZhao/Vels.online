from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .models import Incident
from .serializers import IncidentCreateSerializer, IncidentSerializer, IncidentUpdateSerializer
from .services.events import record_event
from .services.identifiers import next_display_id
from .services.transitions import transition_incident
from .services.visibility import can_view_incident, filter_incidents_for_user


def _require_auth(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
    return None


class IncidentListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err
        qs = filter_incidents_for_user(Incident.objects.select_related("organization", "created_by", "assignee"), request.user)
        return Response(IncidentSerializer(qs, many=True).data)

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err

        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        org_slug = request.data.get("org")
        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        ser = IncidentCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            display_id = next_display_id()
            incident = ser.save(
                organization=org,
                display_id=display_id,
                created_by=request.user,
            )
            record_event(incident, "incident_created", actor=request.user)

        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class IncidentDetailView(APIView):
    def _get_incident(self, request, pk):
        if not request.user.is_authenticated:
            return None, Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            incident = Incident.objects.select_related("organization", "created_by", "assignee").get(pk=pk)
        except Incident.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return incident, None

    def get(self, request, pk):
        incident, err = self._get_incident(request, pk)
        if err:
            return err
        return Response(IncidentSerializer(incident).data)

    def patch(self, request, pk):
        incident, err = self._get_incident(request, pk)
        if err:
            return err

        if not request.user.is_staff:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=incident.organization
            ).exists()
            if not membership:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if "state" in request.data:
            return Response(
                {"detail": "Use /transition/ to change state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = IncidentUpdateSerializer(incident, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        changes = {field: {"old": getattr(incident, field), "new": value} for field, value in ser.validated_data.items()}

        with transaction.atomic():
            incident = ser.save()
            record_event(incident, "incident_updated", actor=request.user, payload={"changes": changes})

        return Response(IncidentSerializer(incident).data)


class IncidentTransitionView(APIView):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related("organization", "created_by", "assignee").get(pk=pk)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=incident.organization
            ).exists()
            if not membership:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        target_state = request.data.get("state")
        if not target_state:
            return Response({"detail": "state is required."}, status=status.HTTP_400_BAD_REQUEST)

        closure_reason = request.data.get("closure_reason")

        try:
            incident = transition_incident(incident, target_state, actor=request.user, closure_reason=closure_reason)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(IncidentSerializer(incident).data)
