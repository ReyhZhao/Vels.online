import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import QueryDict
from django.utils import timezone
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from django.contrib.auth.models import User

from .filters import IncidentFilterSet
from .models import Attachment, Comment, Incident, IncidentDelegation, IncidentEvent, Subject, Task, TaskTemplate, TaskTemplateItem
from .serializers import (
    AttachmentSerializer,
    CommentCreateSerializer,
    CommentPatchSerializer,
    CommentSerializer,
    IncidentCreateSerializer,
    IncidentEventSerializer,
    IncidentSerializer,
    IncidentUpdateSerializer,
    SubjectCreateSerializer,
    SubjectSerializer,
    SubjectUpdateSerializer,
    TaskCreateSerializer,
    TaskPatchSerializer,
    TaskSerializer,
    TaskTemplateItemSerializer,
    TaskTemplateItemWriteSerializer,
    TaskTemplatePatchSerializer,
    TaskTemplateSerializer,
    TaskTemplateWriteSerializer,
)
from .services.events import record_event
from .services.identifiers import next_display_id
from .services.notifications_wiring import notify_comment, notify_incident_alert_if_needed, notify_severity_bump_if_needed
from .services.promote import build_promote_payload, find_open_incidents
from .services.templates import apply_template, auto_apply_for_subject, cancel_template_tasks_on_subject_change
from .services.attachments import confirm_upload, delete_attachment, issue_download_url, issue_upload_url
from .services.delegation import delegate, return_delegation
from .services.transfer import transfer_incident
from .services.transitions import transition_incident
from .services.visibility import can_view_incident, filter_comments_for_user, filter_events_for_user, filter_incidents_for_user

logger = logging.getLogger(__name__)

TRIAGE_STATES = {"new", "triaged"}

SEVERITY_RANK = Case(
    When(severity="critical", then=Value(4)),
    When(severity="high",     then=Value(3)),
    When(severity="medium",   then=Value(2)),
    When(severity="low",      then=Value(1)),
    default=Value(0),
    output_field=IntegerField(),
)

_SORTABLE_FIELDS = {
    "title":      "title",
    "state":      "state",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "assignee":   "assignee__username",
}


def _apply_incident_filters(qs, request):
    tab = request.query_params.get("tab", "all")
    explicit_states = [
        c.strip()
        for v in request.query_params.getlist("state")
        for c in v.split(",")
        if c.strip()
    ]

    # Tab-level base filters: assignee scope + default closed exclusion
    if tab == "my_queue":
        my_delegated_ids = IncidentDelegation.objects.filter(
            user=request.user, returned_at__isnull=True
        ).values_list("incident_id", flat=True)
        qs = qs.filter(Q(assignee=request.user) | Q(id__in=my_delegated_ids))
        if not explicit_states:
            qs = qs.exclude(state="closed")
    elif tab == "unassigned":
        qs = qs.filter(assignee__isnull=True)
        if not explicit_states:
            qs = qs.exclude(state="closed")
    else:
        if not explicit_states:
            qs = qs.exclude(state="closed")

    return IncidentFilterSet(request.query_params, queryset=qs, request=request).qs


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

class IncidentPagination(PageNumberPagination):
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

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count":       {"type": "integer"},
                "page":        {"type": "integer"},
                "per_page":    {"type": "integer"},
                "total_pages": {"type": "integer"},
                "results":     schema,
            },
        }


class IncidentListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = IncidentFilterSet
    pagination_class = IncidentPagination
    serializer_class = IncidentSerializer

    def get_queryset(self):
        qs = Incident.objects.select_related("organization", "created_by", "assignee", "subject")
        qs = filter_incidents_for_user(qs, self.request.user)

        tab = self.request.query_params.get("tab", "all")
        explicit_states = [
            c.strip()
            for v in self.request.query_params.getlist("state")
            for c in v.split(",") if c.strip()
        ]
        if tab == "my_queue":
            delegated = IncidentDelegation.objects.filter(
                user=self.request.user, returned_at__isnull=True
            ).values_list("incident_id", flat=True)
            qs = qs.filter(Q(assignee=self.request.user) | Q(id__in=delegated))
            if not explicit_states:
                qs = qs.exclude(state="closed")
        elif tab == "unassigned":
            qs = qs.filter(assignee__isnull=True)
            if not explicit_states:
                qs = qs.exclude(state="closed")
        else:
            if not explicit_states:
                qs = qs.exclude(state="closed")
        return qs

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        sort = self.request.query_params.get("sort", "")
        order = self.request.query_params.get("order", "")
        if sort == "severity":
            qs = qs.annotate(severity_rank=SEVERITY_RANK)
            qs = qs.order_by("severity_rank" if order == "asc" else "-severity_rank")
        elif sort in _SORTABLE_FIELDS:
            field = _SORTABLE_FIELDS[sort]
            qs = qs.order_by(F(field).asc(nulls_last=True) if order == "asc" else F(field).desc(nulls_last=True))
        else:
            qs = qs.annotate(severity_rank=SEVERITY_RANK).order_by("-severity_rank", "created_at")
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("tab", OpenApiTypes.STR, description="all | my_queue | unassigned"),
            OpenApiParameter("sort", OpenApiTypes.STR, description="severity | title | state | created_at | updated_at | assignee"),
            OpenApiParameter("order", OpenApiTypes.STR, description="asc | desc (default: desc)"),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def post(self, request):
        org_slug = request.data.get("org")
        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
                return Response({"detail": "You are not a member of this organisation."}, status=status.HTTP_403_FORBIDDEN)

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

        notify_incident_alert_if_needed(incident)
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class IncidentBulkActionView(APIView):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get("action")
        select_all = request.data.get("select_all", False)
        ids = request.data.get("ids")

        if action not in ("close", "reassign"):
            return Response(
                {"detail": "action must be 'close' or 'reassign'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if select_all:
            filters = request.data.get("filters", {})
            fake_get = QueryDict(mutable=True)
            fake_get.update(filters)
            original_get = request._request.GET
            request._request.GET = fake_get
            try:
                qs = filter_incidents_for_user(
                    Incident.objects.select_related("organization", "created_by", "assignee"),
                    request.user,
                )
                qs = _apply_incident_filters(qs, request)
                ids = list(qs.values_list("id", flat=True))
            finally:
                request._request.GET = original_get
            if not ids:
                return Response({"detail": "No incidents match the given filters."}, status=400)
        elif not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            return Response(
                {"detail": "ids must be a non-empty list of integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        closure_reason = None
        assignee_id = None

        if action == "close":
            closure_reason = request.data.get("closure_reason")
            if not closure_reason:
                return Response(
                    {"detail": "closure_reason is required for close action."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            valid_reasons = {c[0] for c in Incident.CLOSURE_REASON_CHOICES}
            if closure_reason not in valid_reasons:
                return Response(
                    {"detail": "Invalid closure_reason."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if action == "reassign":
            if "assignee_id" not in request.data:
                return Response(
                    {"detail": "assignee_id is required for reassign action."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            assignee_id = request.data.get("assignee_id")
            if assignee_id is not None and not isinstance(assignee_id, int):
                return Response(
                    {"detail": "assignee_id must be an integer or null."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        qs = filter_incidents_for_user(
            Incident.objects.select_related("organization", "created_by", "assignee"),
            request.user,
        ).filter(id__in=ids)

        incidents_by_id = {inc.id: inc for inc in qs}

        succeeded = []
        failed = []

        for incident_id in ids:
            incident = incidents_by_id.get(incident_id)
            if incident is None:
                continue

            try:
                if action == "close":
                    transition_incident(incident, "closed", actor=request.user, closure_reason=closure_reason)
                    succeeded.append(incident_id)
                else:
                    old_assignee_id = incident.assignee_id
                    incident.assignee_id = assignee_id
                    incident.save(update_fields=["assignee"])
                    record_event(
                        incident,
                        "incident_updated",
                        actor=request.user,
                        payload={"changes": {"assignee_id": {"old": old_assignee_id, "new": assignee_id}}},
                    )
                    succeeded.append(incident_id)
            except ValidationError as e:
                msg = e.messages[0] if e.messages else str(e)
                failed.append({"id": incident_id, "error": msg})

        return Response({"succeeded": succeeded, "failed": failed})


class IncidentDetailView(APIView):
    def _get_incident(self, request, display_id):
        if not request.user.is_authenticated:
            return None, Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(display_id=display_id)
        except Incident.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return incident, None

    def get(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        return Response(IncidentSerializer(incident).data)

    def patch(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
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

        old_subject = incident.subject
        old_severity = incident.severity

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
            if "subject" in ser.validated_data and old_subject != incident.subject:
                if old_subject is not None:
                    cancel_template_tasks_on_subject_change(incident, old_subject, actor=request.user)
                if incident.subject is not None:
                    auto_apply_for_subject(incident, actor=request.user)

        if "severity" in ser.validated_data:
            notify_severity_bump_if_needed(incident, old_severity)

        return Response(IncidentSerializer(incident).data)


class IncidentTransitionView(APIView):
    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(display_id=display_id)
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


class IncidentTransferView(APIView):
    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        assignee_id = request.data.get("assignee_id")
        if not assignee_id:
            return Response({"detail": "assignee_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_assignee = User.objects.get(pk=assignee_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            incident = transfer_incident(incident, new_assignee, actor=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(IncidentSerializer(incident).data)


class StaffUserListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err
        users = User.objects.filter(is_staff=True, is_active=True).order_by("username")
        data = [{"id": u.id, "username": u.username} for u in users]
        return Response(data)


class IncidentTimelineView(APIView):
    PAGE_SIZE = 50

    def get(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            incident = Incident.objects.select_related("organization", "assignee").get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff and incident.tlp == "amber":
            return Response({"detail": "Timeline not available at TLP:AMBER."}, status=status.HTTP_403_FORBIDDEN)

        qs = (
            IncidentEvent.objects
            .filter(incident=incident)
            .select_related("actor")
            .order_by("created_at", "id")
        )
        qs = filter_events_for_user(qs, request.user, incident)

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1

        total = qs.count()
        start = (page - 1) * self.PAGE_SIZE
        events = qs[start: start + self.PAGE_SIZE]

        return Response({
            "count": total,
            "page": page,
            "page_size": self.PAGE_SIZE,
            "results": IncidentEventSerializer(events, many=True).data,
        })


class IncidentDelegateView(APIView):
    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delegate_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get("note", "")

        try:
            delegate(incident, delegate_user, by=request.user, note=note)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        incident.refresh_from_db()
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class IncidentDelegationReturnView(APIView):
    def post(self, request, display_id, delegation_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            incident = Incident.objects.select_related(
                "organization", "created_by", "assignee", "subject"
            ).get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            delegation = IncidentDelegation.objects.select_related("user", "incident__assignee").get(
                pk=delegation_id, incident=incident
            )
        except IncidentDelegation.DoesNotExist:
            return Response({"detail": "Delegation not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            return_delegation(delegation, by=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        incident.refresh_from_db()
        return Response(IncidentSerializer(incident).data)


# ── Task views ───────────────────────────────────────────────────────────────

def _get_incident_for_user(request, display_id):
    if not request.user.is_authenticated:
        return None, Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
    try:
        incident = Incident.objects.select_related("organization", "subject").get(display_id=display_id)
    except Incident.DoesNotExist:
        return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if not can_view_incident(request.user, incident):
        return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return incident, None


class IncidentTaskListView(APIView):
    def get(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        tasks = (
            Task.objects
            .filter(incident=incident)
            .select_related("template_item__template", "assignee")
        )
        return Response(TaskSerializer(tasks, many=True).data)

    def post(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        if not request.user.is_staff:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=incident.organization
            ).exists()
            if not membership:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        ser = TaskCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            task = ser.save(incident=incident)
            record_event(
                incident, "task_created", actor=request.user,
                payload={"task_id": task.id, "title": task.title, "created_at": task.created_at.isoformat()},
            )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class ApplyTemplateView(APIView):
    def post(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        if not request.user.is_staff:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=incident.organization
            ).exists()
            if not membership:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        template_id = request.data.get("template_id")
        if not template_id:
            return Response({"detail": "template_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            template = TaskTemplate.objects.get(pk=template_id)
        except TaskTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            apply_template(incident, template, actor=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)
        tasks = (
            Task.objects
            .filter(incident=incident)
            .select_related("template_item__template", "assignee")
        )
        return Response(TaskSerializer(tasks, many=True).data, status=status.HTTP_201_CREATED)


_TASK_SORT_FIELDS = {
    "title":      "title",
    "state":      "state",
    "created_at": "created_at",
    "incident":   "incident__display_id",
    "assignee":   "assignee__username",
}


class TaskListView(APIView):
    def get(self, request):
        err = _require_auth(request)
        if err:
            return err

        visible_ids = filter_incidents_for_user(
            Incident.objects.all(), request.user
        ).values_list("id", flat=True)

        qs = (
            Task.objects
            .filter(incident_id__in=visible_ids)
            .select_related("incident", "assignee", "template_item__template")
        )

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)

        state = request.query_params.get("state", "").strip()
        if state:
            qs = qs.filter(state=state)

        assignee = request.query_params.get("assignee", "").strip()
        if assignee == "me":
            qs = qs.filter(assignee=request.user)
        elif assignee == "unassigned":
            qs = qs.filter(assignee__isnull=True)

        sort = request.query_params.get("sort", "")
        order = request.query_params.get("order", "")
        if sort in _TASK_SORT_FIELDS:
            field = _TASK_SORT_FIELDS[sort]
            if order == "asc":
                qs = qs.order_by(F(field).asc(nulls_last=True))
            else:
                qs = qs.order_by(F(field).desc(nulls_last=True))
        else:
            qs = qs.order_by("-created_at")

        try:
            per_page = min(max(1, int(request.query_params.get("per_page", 25))), 100)
        except (ValueError, TypeError):
            per_page = 25
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1

        total = qs.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        results = qs[start : start + per_page]

        return Response({
            "count": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "results": TaskSerializer(results, many=True).data,
        })


class TaskDetailView(APIView):
    def _get_task(self, request, pk):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            task = Task.objects.select_related(
                "incident__organization", "template_item__template", "assignee"
            ).get(pk=pk)
        except Task.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, task.incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return task, None

    def get(self, request, pk):
        task, err = self._get_task(request, pk)
        if err:
            return err
        return Response(TaskSerializer(task).data)

    def patch(self, request, pk):
        task, err = self._get_task(request, pk)
        if err:
            return err
        if not request.user.is_staff:
            membership = OrganizationMembership.objects.filter(
                user=request.user, organization=task.incident.organization
            ).exists()
            if not membership:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        old_state = task.state
        old_assignee_id = task.assignee_id
        ser = TaskPatchSerializer(task, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            task = ser.save()
            closed_states = {Task.STATE_DONE, Task.STATE_CANCELLED}
            if task.state in closed_states and old_state not in closed_states:
                Task.objects.filter(pk=task.pk).update(closed_at=timezone.now())
                task.refresh_from_db()
            if old_state != task.state:
                record_event(
                    task.incident, "task_state_changed", actor=request.user,
                    payload={"task_id": task.id, "title": task.title, "old": old_state, "new": task.state,
                         "created_at": task.created_at.isoformat(), "closed_at": task.closed_at.isoformat() if task.closed_at else None},
                )
            if old_assignee_id != task.assignee_id:
                record_event(
                    task.incident, "task_assignee_changed", actor=request.user,
                    payload={"task_id": task.id, "title": task.title,
                             "old": old_assignee_id, "new": task.assignee_id},
                )
        return Response(TaskSerializer(task).data)


class TaskRunView(APIView):
    def post(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.select_related("incident", "automation").get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, task.incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if task.task_type != Task.TYPE_AUTOMATED:
            return Response({"detail": "Task is not of type automated."}, status=status.HTTP_400_BAD_REQUEST)
        if not task.automation_id:
            return Response({"detail": "Task has no automation attached."}, status=status.HTTP_400_BAD_REQUEST)

        from automations.semaphore import SemaphoreAPIError, SemaphoreClient
        incident = task.incident
        extra_vars = dict(task.automation.default_vars or {})
        extra_vars.update({
            "incident_id": incident.id,
            "incident_display_id": incident.display_id,
            "incident_title": incident.title,
            "incident_severity": incident.severity,
        })
        try:
            client = SemaphoreClient()
            semaphore_task_id = client.launch_job(
                template_id=task.automation.semaphore_template_id,
                extra_vars=extra_vars,
            )
        except SemaphoreAPIError as exc:
            logger.error(
                "launch_job failed for task=%s automation=%s template_id=%s: status=%s body=%r extra_vars=%s",
                task.pk,
                task.automation_id,
                task.automation.semaphore_template_id,
                exc.status_code,
                exc.body,
                extra_vars,
            )
            return Response({"detail": f"Semaphore error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        Task.objects.filter(pk=task.pk).update(
            semaphore_task_id=semaphore_task_id,
            state=Task.STATE_IN_PROGRESS,
            automation_error=None,
        )
        task.refresh_from_db()
        return Response(TaskSerializer(task).data)


# ── Promote view ─────────────────────────────────────────────────────────────

class PromoteView(APIView):
    def post(self, request):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        source_kind = request.data.get("source_kind")
        source_ref = request.data.get("source_ref") or {}

        if not source_kind:
            return Response({"detail": "source_kind is required."}, status=status.HTTP_400_BAD_REQUEST)

        form_payload = build_promote_payload(source_kind, source_ref)
        open_incidents_qs = find_open_incidents(source_kind, source_ref)

        if not request.data.get("commit", False):
            return Response({
                "form_payload": form_payload,
                "open_incidents": IncidentSerializer(open_incidents_qs, many=True).data,
            })

        org_slug = request.data.get("org")
        if not org_slug:
            return Response({"detail": "org is required when commit=true."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        create_data = dict(form_payload)
        for field in ["title", "description", "severity", "tlp", "pap", "subject", "assignee"]:
            if field in request.data:
                create_data[field] = request.data[field]

        ser = IncidentCreateSerializer(data=create_data)
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


# ── Comment views ─────────────────────────────────────────────────────────────

class IncidentCommentListView(APIView):
    def get(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        qs = (
            Comment.objects
            .filter(incident=incident, task__isnull=True)
            .select_related("author")
        )
        qs = filter_comments_for_user(qs, request.user, incident)
        return Response(CommentSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        ser = CommentCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        comment = ser.save(incident=incident, author=request.user)
        record_event(
            incident, "comment_added", actor=request.user,
            payload={"target_type": "comment", "target_id": comment.id, "is_internal": comment.is_internal},
        )
        notify_comment(incident, comment, actor=request.user)
        return Response(CommentSerializer(comment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class TaskCommentListView(APIView):
    def _get_task(self, request, pk):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            task = Task.objects.select_related("incident__organization").get(pk=pk)
        except Task.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, task.incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return task, None

    def get(self, request, pk):
        task, err = self._get_task(request, pk)
        if err:
            return err
        qs = Comment.objects.filter(task=task).select_related("author")
        qs = filter_comments_for_user(qs, request.user, task.incident)
        return Response(CommentSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request, pk):
        task, err = self._get_task(request, pk)
        if err:
            return err
        ser = CommentCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        comment = ser.save(incident=task.incident, task=task, author=request.user)
        record_event(
            task.incident, "comment_added", actor=request.user,
            payload={"target_type": "comment", "target_id": comment.id, "is_internal": comment.is_internal},
        )
        return Response(CommentSerializer(comment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CommentDetailView(APIView):
    def _get_comment(self, request, pk):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            comment = Comment.objects.select_related("incident__organization", "author").get(pk=pk)
        except Comment.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, comment.incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return comment, None

    def patch(self, request, pk):
        comment, err = self._get_comment(request, pk)
        if err:
            return err
        if comment.deleted_at:
            return Response({"detail": "Cannot edit a deleted comment."}, status=status.HTTP_400_BAD_REQUEST)
        if comment.author_id != request.user.id:
            return Response({"detail": "Only the author may edit this comment."}, status=status.HTTP_403_FORBIDDEN)
        if (timezone.now() - comment.created_at).total_seconds() >= 900:
            return Response({"detail": "Edit window has closed."}, status=status.HTTP_403_FORBIDDEN)
        ser = CommentPatchSerializer(comment, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        updated = ser.save()
        record_event(
            comment.incident, "comment_edited", actor=request.user,
            payload={"target_type": "comment", "target_id": comment.id, "is_internal": comment.is_internal},
        )
        return Response(CommentSerializer(updated, context={"request": request}).data)

    def delete(self, request, pk):
        comment, err = self._get_comment(request, pk)
        if err:
            return err
        if comment.deleted_at:
            return Response({"detail": "Already deleted."}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        is_author_in_window = (
            comment.author_id == request.user.id and
            (now - comment.created_at).total_seconds() < 900
        )
        if not is_author_in_window and not request.user.is_staff:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        comment.deleted_at = now
        comment.save(update_fields=["deleted_at"])
        record_event(
            comment.incident, "comment_deleted", actor=request.user,
            payload={"target_type": "comment", "target_id": comment.id, "is_internal": comment.is_internal},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Attachment views ──────────────────────────────────────────────────────────

class IncidentAttachmentListView(APIView):
    def get(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err
        qs = (
            Attachment.objects
            .filter(incident=incident, confirmed_at__isnull=False, deleted_at__isnull=True)
            .select_related("uploader")
        )
        if not request.user.is_staff:
            qs = qs.filter(is_internal=False)
        return Response(AttachmentSerializer(qs, many=True).data)

    def post(self, request, display_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err

        filename = request.data.get("filename", "").strip()
        content_type = request.data.get("content_type", "application/octet-stream").strip()
        if not filename:
            return Response({"detail": "filename is required."}, status=status.HTTP_400_BAD_REQUEST)

        is_internal = request.data.get("is_internal", True)
        if isinstance(is_internal, str):
            is_internal = is_internal.lower() not in ("false", "0", "no")

        try:
            attachment, upload_url = issue_upload_url(
                incident, filename, content_type, uploader=request.user, is_internal=bool(is_internal)
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {"attachment": AttachmentSerializer(attachment).data, "upload_url": upload_url},
            status=status.HTTP_201_CREATED,
        )


class IncidentAttachmentConfirmView(APIView):
    def post(self, request, display_id, attachment_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err

        try:
            attachment = Attachment.objects.select_related("uploader", "incident").get(
                pk=attachment_id, incident=incident, deleted_at__isnull=True
            )
        except Attachment.DoesNotExist:
            return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        if attachment.confirmed_at is not None:
            return Response({"detail": "Already confirmed."}, status=status.HTTP_400_BAD_REQUEST)

        if attachment.uploader_id != request.user.id and not request.user.is_staff:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        try:
            attachment = confirm_upload(attachment)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AttachmentSerializer(attachment).data)


class IncidentAttachmentDownloadView(APIView):
    def get(self, request, display_id, attachment_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err

        try:
            attachment = Attachment.objects.get(
                pk=attachment_id, incident=incident,
                confirmed_at__isnull=False, deleted_at__isnull=True,
            )
        except Attachment.DoesNotExist:
            return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        if attachment.is_internal and not request.user.is_staff:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            url = issue_download_url(attachment)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"url": url})


class IncidentAttachmentDeleteView(APIView):
    def delete(self, request, display_id, attachment_id):
        incident, err = _get_incident_for_user(request, display_id)
        if err:
            return err

        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            attachment = Attachment.objects.get(
                pk=attachment_id, incident=incident, deleted_at__isnull=True
            )
        except Attachment.DoesNotExist:
            return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            delete_attachment(attachment, actor=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=status.HTTP_204_NO_CONTENT)
