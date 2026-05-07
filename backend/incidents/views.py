from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .models import Incident, Subject, TaskTemplate, TaskTemplateItem
from .serializers import (
    IncidentCreateSerializer,
    IncidentSerializer,
    IncidentUpdateSerializer,
    SubjectCreateSerializer,
    SubjectSerializer,
    SubjectUpdateSerializer,
    TaskTemplateItemSerializer,
    TaskTemplateItemWriteSerializer,
    TaskTemplatePatchSerializer,
    TaskTemplateSerializer,
    TaskTemplateWriteSerializer,
)
from .services.events import record_event
from .services.identifiers import next_display_id
from .services.transitions import transition_incident
from .services.visibility import can_view_incident, filter_incidents_for_user

TRIAGE_STATES = {"new", "triaged"}


def _require_auth(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
    return None


# ── Subject views ────────────────────────────────────────────────────────────

class SubjectListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err
        qs = Subject.objects.all()
        return Response(SubjectSerializer(qs, many=True).data)

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        ser = SubjectCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        name = ser.validated_data["name"]
        slug = slugify(name)
        if Subject.objects.filter(slug=slug).exists():
            return Response({"detail": "A subject with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)
        subject = ser.save(slug=slug)
        return Response(SubjectSerializer(subject).data, status=status.HTTP_201_CREATED)


class SubjectDetailView(APIView):
    def _get_subject(self, pk):
        try:
            return Subject.objects.get(pk=pk), None
        except Subject.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        subject, err = self._get_subject(pk)
        if err:
            return err
        return Response(SubjectSerializer(subject).data)

    def patch(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        subject, err = self._get_subject(pk)
        if err:
            return err
        ser = SubjectUpdateSerializer(subject, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        return Response(SubjectSerializer(subject).data)


# ── TaskTemplate views ───────────────────────────────────────────────────────

class TaskTemplateListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err
        qs = TaskTemplate.objects.select_related("subject", "created_by").prefetch_related("items")
        subject_id = request.query_params.get("subject")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        return Response(TaskTemplateSerializer(qs, many=True).data)

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        ser = TaskTemplateWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        template = ser.save(created_by=request.user)
        template.refresh_from_db()
        return Response(
            TaskTemplateSerializer(TaskTemplate.objects.prefetch_related("items").get(pk=template.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class TaskTemplateDetailView(APIView):
    def _get_template(self, pk):
        try:
            return TaskTemplate.objects.select_related("subject", "created_by").prefetch_related("items").get(pk=pk), None
        except TaskTemplate.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        template, err = self._get_template(pk)
        if err:
            return err
        return Response(TaskTemplateSerializer(template).data)

    def patch(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        template, err = self._get_template(pk)
        if err:
            return err
        ser = TaskTemplatePatchSerializer(template, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        return Response(TaskTemplateSerializer(
            TaskTemplate.objects.prefetch_related("items").get(pk=pk)
        ).data)

    def delete(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        template, err = self._get_template(pk)
        if err:
            return err
        template.archived = True
        template.save(update_fields=["archived", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskTemplateItemListView(APIView):
    def _get_template(self, pk, request):
        err = _require_auth(request)
        if err:
            return None, err
        if not request.user.is_staff:
            return None, Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            return TaskTemplate.objects.get(pk=pk), None
        except TaskTemplate.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, pk):
        template, err = self._get_template(pk, request)
        if err:
            return err
        ser = TaskTemplateItemWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        item = ser.save(template=template)
        return Response(TaskTemplateItemSerializer(item).data, status=status.HTTP_201_CREATED)


class TaskTemplateItemDetailView(APIView):
    def _get_item(self, template_pk, item_pk, request):
        err = _require_auth(request)
        if err:
            return None, err
        if not request.user.is_staff:
            return None, Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            return TaskTemplateItem.objects.get(pk=item_pk, template_id=template_pk), None
        except TaskTemplateItem.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk, item_pk):
        item, err = self._get_item(pk, item_pk, request)
        if err:
            return err
        ser = TaskTemplateItemWriteSerializer(item, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        ser.save()
        return Response(TaskTemplateItemSerializer(item).data)

    def delete(self, request, pk, item_pk):
        item, err = self._get_item(pk, item_pk, request)
        if err:
            return err
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Incident views ───────────────────────────────────────────────────────────

class IncidentListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err
        qs = filter_incidents_for_user(
            Incident.objects.select_related("organization", "created_by", "assignee", "subject"),
            request.user,
        )
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
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(pk=pk)
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

        if "subject" in request.data and incident.state not in TRIAGE_STATES:
            return Response(
                {"detail": "Subject can only be changed while the incident is in new or triaged state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = IncidentUpdateSerializer(incident, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        changes = {}
        for field, value in ser.validated_data.items():
            if field == "subject":
                changes[field] = {
                    "old": incident.subject.slug if incident.subject else None,
                    "new": value.slug if value else None,
                }
            else:
                changes[field] = {"old": getattr(incident, field), "new": value}

        with transaction.atomic():
            incident = ser.save()
            record_event(incident, "incident_updated", actor=request.user, payload={"changes": changes})

        return Response(IncidentSerializer(incident).data)


class IncidentTransitionView(APIView):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(pk=pk)
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
