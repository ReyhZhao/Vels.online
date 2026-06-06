import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import QueryDict
from django.utils import timezone
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as _s
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from django.contrib.auth.models import User

from .filters import AssetFilterSet, IncidentFilterSet, TaskFilterSet, TaskTemplateFilterSet
from .models import Asset, Attachment, Comment, IOC, Incident, IncidentAsset, IncidentDelegation, IncidentEvent, Subject, Task, TaskTemplate, TaskTemplateItem, WazuhResponseExecution
from .serializers import (
    AssetSerializer,
    AttachmentSerializer,
    CommentCreateSerializer,
    CommentPatchSerializer,
    CommentSerializer,
    IncidentAssetSerializer,
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
from .services.assets import link_asset_from_source_ref
from .services.ioc_extraction import extract_and_save_iocs
from .services.events import record_event
from .services.identifiers import next_display_id
from .services.notifications_wiring import notify_comment, notify_incident_alert_if_needed, notify_severity_bump_if_needed
from .services.promote import build_promote_payload, find_open_incidents, link_source_assets
from .services.templates import apply_template, auto_apply_for_subject, cancel_template_tasks_on_subject_change
from .services.attachments import confirm_upload, delete_attachment, issue_download_url, issue_upload_url
from .services.delegation import delegate, return_delegation
from .services.transfer import transfer_incident
from .services.transitions import transition_incident
from .services.visibility import can_view_incident, filter_comments_for_user, filter_events_for_user, filter_incidents_for_user
from .tasks import acquire_triage_lock, enrich_iocs_then_triage, run_incident_triage

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

class TaskTemplateListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskTemplateFilterSet
    serializer_class = TaskTemplateSerializer

    def get_queryset(self):
        return TaskTemplate.objects.select_related("subject", "created_by").prefetch_related("items")

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

    @extend_schema(
        summary="Create incident",
        description="Create a new incident for an organisation. Requires staff or org membership.",
        request=inline_serializer(
            name="IncidentCreateRequest",
            fields={
                "org": _s.CharField(help_text="Organisation slug"),
                "title": _s.CharField(),
                "description": _s.CharField(required=False, allow_blank=True),
                "severity": _s.ChoiceField(
                    choices=["critical", "high", "medium", "low", "info"],
                    help_text="Severity level",
                ),
                "tlp": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    help_text="TLP classification",
                ),
                "pap": _s.ChoiceField(
                    choices=["white", "green", "amber", "red"],
                    required=False,
                    help_text="PAP classification",
                ),
                "source_kind": _s.CharField(required=False, allow_blank=True, allow_null=True),
                "source_ref": _s.DictField(required=False, allow_null=True, help_text="Source-specific metadata"),
                "subject": _s.IntegerField(required=False, allow_null=True, help_text="Subject PK"),
                "assignee": _s.IntegerField(required=False, allow_null=True, help_text="Assignee user PK"),
            },
        ),
        responses={201: IncidentSerializer},
    )
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
            link_asset_from_source_ref(incident, incident.source_kind, incident.source_ref)
            extract_and_save_iocs(incident)

        notify_incident_alert_if_needed(incident)
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)


class AssetListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = AssetFilterSet
    serializer_class = AssetSerializer

    def get_queryset(self):
        qs = Asset.objects.select_related("route", "organization")
        if not self.request.user.is_staff:
            member_org_ids = OrganizationMembership.objects.filter(
                user=self.request.user
            ).values_list("organization_id", flat=True)
            qs = qs.filter(organization__in=member_org_ids)
        return qs

    def post(self, request):
        err = _require_auth(request)
        if err:
            return err

        kind = request.data.get("kind")
        org_slug = request.data.get("organization")
        name = request.data.get("name")

        if not kind:
            return Response({"detail": "kind is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not org_slug:
            return Response({"detail": "organization is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not name:
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        if kind == Asset.KIND_HOST:
            agent_name = request.data.get("agent_name")
            if not agent_name:
                return Response({"detail": "agent_name is required for host assets."}, status=status.HTTP_400_BAD_REQUEST)
            if Asset.objects.filter(organization=org, kind=Asset.KIND_HOST, agent_name=agent_name).exists():
                return Response(
                    {"detail": "A host asset with this agent_name already exists for this organisation."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            asset = Asset.objects.create(
                organization=org,
                kind=Asset.KIND_HOST,
                name=name,
                agent_name=agent_name,
                ip_address=request.data.get("ip_address") or None,
                is_permanent=bool(request.data.get("is_permanent", False)),
            )

        elif kind == Asset.KIND_ROUTE:
            from ingress.models import Route
            route_id = request.data.get("route")
            if not route_id:
                return Response({"detail": "route is required for route assets."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                route = Route.objects.get(pk=route_id)
            except Route.DoesNotExist:
                return Response({"detail": "Route not found."}, status=status.HTTP_404_NOT_FOUND)
            if Asset.objects.filter(kind=Asset.KIND_ROUTE, route=route).exists():
                return Response({"detail": "An asset already exists for this route."}, status=status.HTTP_400_BAD_REQUEST)
            asset = Asset.objects.create(
                organization=org,
                kind=Asset.KIND_ROUTE,
                name=name,
                route=route,
            )

        else:
            return Response({"detail": "kind must be 'host' or 'route'."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class AssetBulkUpdateView(APIView):
    """Bulk-update is_permanent and/or owners across multiple assets."""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        is_permanent = request.data.get("is_permanent")
        owner_ids = request.data.get("owner_ids")

        if is_permanent is None and owner_ids is None:
            return Response({"detail": "Provide at least one of: is_permanent, owner_ids."}, status=status.HTTP_400_BAD_REQUEST)

        qs = Asset.objects.filter(pk__in=ids)
        if not request.user.is_staff:
            member_org_ids = OrganizationMembership.objects.filter(
                user=request.user
            ).values_list("organization_id", flat=True)
            qs = qs.filter(organization__in=member_org_ids)

        assets = list(qs)
        if not assets:
            return Response({"detail": "No accessible assets found for the given ids."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            if is_permanent is not None:
                Asset.objects.filter(pk__in=[a.pk for a in assets]).update(is_permanent=bool(is_permanent))

            if owner_ids is not None:
                from contacts.models import AssetOwner, Contact
                valid_owners = list(Contact.objects.filter(pk__in=owner_ids))
                for asset in assets:
                    AssetOwner.objects.filter(asset=asset).delete()
                    AssetOwner.objects.bulk_create(
                        [AssetOwner(asset=asset, contact=c) for c in valid_owners
                         if c.organisation_id == asset.organization_id],
                        ignore_conflicts=True,
                    )

        updated = Asset.objects.filter(pk__in=[a.pk for a in assets]).select_related("route", "organization")
        return Response(AssetSerializer(updated, many=True).data)


def _get_asset_for_user(user, pk):
    try:
        asset = Asset.objects.select_related("organization", "route").get(pk=pk)
    except Asset.DoesNotExist:
        return None, Response(status=status.HTTP_404_NOT_FOUND)
    if not user.is_staff:
        if not OrganizationMembership.objects.filter(user=user, organization=asset.organization).exists():
            return None, Response(status=status.HTTP_404_NOT_FOUND)
    return asset, None


class AssetDetailView(APIView):
    def get(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        asset, err = _get_asset_for_user(request.user, pk)
        if err:
            return err
        return Response(AssetSerializer(asset).data)

    def patch(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        asset, err = _get_asset_for_user(request.user, pk)
        if err:
            return err
        allowed = {}
        if "name" in request.data:
            allowed["name"] = request.data["name"]
        if "ip_address" in request.data:
            allowed["ip_address"] = request.data["ip_address"] or None
        if "is_permanent" in request.data:
            allowed["is_permanent"] = bool(request.data["is_permanent"])
        if not allowed:
            return Response(AssetSerializer(asset).data)
        for field, value in allowed.items():
            setattr(asset, field, value)
        asset.save(update_fields=list(allowed.keys()))
        return Response(AssetSerializer(asset).data)

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        asset, err = _get_asset_for_user(request.user, pk)
        if err:
            return err
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssetOwnerListView(APIView):
    def _get_asset(self, request, pk):
        if not request.user.is_authenticated:
            return None, Response(status=status.HTTP_401_UNAUTHORIZED)
        return _get_asset_for_user(request.user, pk)

    def get(self, request, pk):
        asset, err = self._get_asset(request, pk)
        if err:
            return err
        from contacts.models import AssetOwner
        from contacts.serializers import ContactSerializer
        contacts = asset.asset_ownerships.select_related("contact").values_list("contact", flat=False)
        from contacts.models import Contact
        qs = Contact.objects.filter(asset_ownerships__asset=asset)
        return Response(ContactSerializer(qs, many=True).data)

    def post(self, request, pk):
        asset, err = self._get_asset(request, pk)
        if err:
            return err
        contact_id = request.data.get("contact_id")
        if not contact_id:
            return Response({"detail": "contact_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        from contacts.models import AssetOwner, Contact
        from contacts.serializers import ContactSerializer
        try:
            contact = Contact.objects.get(pk=contact_id)
        except Contact.DoesNotExist:
            return Response({"detail": "Contact not found."}, status=status.HTTP_400_BAD_REQUEST)
        if contact.organisation_id != asset.organization_id:
            return Response({"detail": "Contact belongs to a different organisation."}, status=status.HTTP_400_BAD_REQUEST)
        AssetOwner.objects.get_or_create(asset=asset, contact=contact)
        qs = Contact.objects.filter(asset_ownerships__asset=asset)
        return Response(ContactSerializer(qs, many=True).data, status=status.HTTP_201_CREATED)


class AssetOwnerDetailView(APIView):
    def delete(self, request, pk, contact_pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        asset, err = _get_asset_for_user(request.user, pk)
        if err:
            return err
        from contacts.models import AssetOwner
        deleted, _ = AssetOwner.objects.filter(asset=asset, contact_id=contact_pk).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentAssetLinkView(APIView):
    def post(self, request, display_id):
        err = _require_auth(request)
        if err:
            return err

        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        asset_id = request.data.get("asset")
        if not asset_id:
            return Response({"detail": "asset is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            return Response({"detail": "Asset not found."}, status=status.HTTP_404_NOT_FOUND)

        if IncidentAsset.objects.filter(incident=incident, asset=asset).exists():
            return Response({"detail": "Asset already linked to this incident."}, status=status.HTTP_400_BAD_REQUEST)

        link = IncidentAsset.objects.create(incident=incident, asset=asset, added_by=request.user)
        from incidents.services.contacts import auto_link_contacts_for_asset
        auto_link_contacts_for_asset(incident, asset)
        return Response(IncidentAssetSerializer(link).data, status=status.HTTP_201_CREATED)


class IncidentAssetUnlinkView(APIView):
    def delete(self, request, display_id, asset_id):
        err = _require_auth(request)
        if err:
            return err

        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            link = IncidentAsset.objects.get(incident=incident, asset_id=asset_id)
        except IncidentAsset.DoesNotExist:
            return Response({"detail": "Asset not linked to this incident."}, status=status.HTTP_404_NOT_FOUND)

        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _serialize_incident_contact(r):
    return {
        "id": r.id,
        "contact_id": r.contact_id,
        "name": r.contact.name,
        "email": r.contact.email,
        "created_at": r.created_at,
    }


def _serialize_contact_message(msg):
    return {
        "id": msg.id,
        "contact_id": msg.contact_id,
        "direction": msg.direction,
        "role": msg.role,
        "body": msg.body,
        "parent_id": msg.parent_id,
        "read_at": msg.read_at,
        "created_at": msg.created_at,
    }


class IncidentContactListView(APIView):
    def _get_incident(self, request, display_id):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return incident, None

    def get(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        from contacts.models import IncidentContact
        rows = IncidentContact.objects.filter(incident=incident).select_related("contact")
        return Response([_serialize_incident_contact(r) for r in rows])

    def post(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        from contacts.models import Contact, IncidentContact
        contact_id = request.data.get("contact_id")
        if not contact_id:
            return Response({"detail": "contact_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            contact = Contact.objects.get(pk=contact_id)
        except Contact.DoesNotExist:
            return Response({"detail": "Contact not found."}, status=status.HTTP_400_BAD_REQUEST)
        if contact.organisation_id != incident.organization_id:
            return Response({"detail": "Contact belongs to a different organisation."}, status=status.HTTP_400_BAD_REQUEST)
        if IncidentContact.objects.filter(incident=incident, contact=contact).exists():
            return Response({"detail": "Contact already linked to this incident."}, status=status.HTTP_400_BAD_REQUEST)
        row = IncidentContact.objects.create(incident=incident, contact=contact)
        row.refresh_from_db()
        row.contact = contact
        return Response(_serialize_incident_contact(row), status=status.HTTP_201_CREATED)


class IncidentContactDetailView(APIView):
    def _get_row(self, request, display_id, pk):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return None, Response(status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return None, Response(status=status.HTTP_404_NOT_FOUND)
        from contacts.models import IncidentContact
        try:
            row = IncidentContact.objects.select_related("contact").get(pk=pk, incident=incident)
        except IncidentContact.DoesNotExist:
            return None, Response(status=status.HTTP_404_NOT_FOUND)
        return row, None

    def delete(self, request, display_id, pk):
        row, err = self._get_row(request, display_id, pk)
        if err:
            return err
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentContactMessageListView(APIView):
    def _get_incident(self, request, display_id):
        err = _require_auth(request)
        if err:
            return None, err
        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return incident, None

    def get(self, request, display_id):
        from collections import defaultdict

        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        from contacts.models import ContactMessage, IncidentContact

        messages = (
            ContactMessage.objects.filter(incident=incident)
            .select_related("contact")
            .order_by("created_at")
        )

        groups = defaultdict(lambda: {"contact_id": None, "name": "", "email": "", "department": "", "messages": []})
        for msg in messages:
            g = groups[msg.contact_id]
            g["contact_id"] = msg.contact_id
            g["name"] = msg.contact.name
            g["email"] = msg.contact.email
            g["department"] = msg.contact.department
            g["messages"].append(_serialize_contact_message(msg))

        linked = IncidentContact.objects.filter(incident=incident).select_related("contact")
        for lc in linked:
            if lc.contact_id not in groups:
                groups[lc.contact_id] = {
                    "contact_id": lc.contact_id,
                    "name": lc.contact.name,
                    "email": lc.contact.email,
                    "department": lc.contact.department,
                    "messages": [],
                }

        return Response(list(groups.values()))

    def post(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        from contacts.models import Contact, ContactMessage
        from contacts.services import send_contact_message

        contact_id = request.data.get("contact_id")
        role = request.data.get("role", "")
        body = request.data.get("body", "")

        if not contact_id:
            return Response({"detail": "contact_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if role not in (ContactMessage.ROLE_NOTIFIED, ContactMessage.ROLE_QUESTIONED):
            return Response({"detail": "role must be 'notified' or 'questioned'."}, status=status.HTTP_400_BAD_REQUEST)
        if not body.strip():
            return Response({"detail": "body is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            contact = Contact.objects.get(pk=contact_id)
        except Contact.DoesNotExist:
            return Response({"detail": "Contact not found."}, status=status.HTTP_400_BAD_REQUEST)
        if contact.organisation_id != incident.organization_id:
            return Response({"detail": "Contact belongs to a different organisation."}, status=status.HTTP_400_BAD_REQUEST)

        msg = send_contact_message(incident, contact, role, body)
        return Response(_serialize_contact_message(msg), status=status.HTTP_201_CREATED)


class IncidentContactMessageMarkReadView(APIView):
    def post(self, request, display_id):
        from django.utils import timezone

        err = _require_auth(request)
        if err:
            return err
        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        contact_id = request.data.get("contact_id")
        if not contact_id:
            return Response({"detail": "contact_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        from contacts.models import ContactMessage

        ContactMessage.objects.filter(
            incident=incident,
            contact_id=contact_id,
            direction=ContactMessage.DIRECTION_INBOUND,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

        return Response({"status": "ok"})


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
        duplicate_of_id = None
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
            if closure_reason == "duplicate":
                duplicate_of_id = request.data.get("duplicate_of")
                if not duplicate_of_id:
                    return Response(
                        {"detail": "duplicate_of is required when closure_reason is duplicate."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not isinstance(duplicate_of_id, int):
                    return Response(
                        {"detail": "duplicate_of must be an integer."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if ids and duplicate_of_id in ids:
                    return Response(
                        {"detail": "The canonical incident cannot be one of the incidents being closed."},
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
                    transition_incident(incident, "closed", actor=request.user, closure_reason=closure_reason, duplicate_of_id=duplicate_of_id)
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
                msg = e.messages[0] if e.messages else "Validation error."
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
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        target_state = request.data.get("state")
        if not target_state:
            return Response({"detail": "state is required."}, status=status.HTTP_400_BAD_REQUEST)

        closure_reason = request.data.get("closure_reason")
        duplicate_of_id = request.data.get("duplicate_of")
        assignee_id = request.data.get("assignee_id")

        try:
            incident = transition_incident(
                incident,
                target_state,
                actor=request.user,
                closure_reason=closure_reason,
                duplicate_of_id=duplicate_of_id,
                assignee_id=assignee_id,
            )
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


class IncidentLinkedAlertsView(APIView):
    """GET /api/incidents/<display_id>/alerts/ — linked alerts for an incident."""

    def get(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            incident = Incident.objects.select_related("organization", "assignee").get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from alerts.models import Alert

        alerts = Alert.objects.filter(incident=incident).select_related("acknowledged_by").order_by("-created_at")
        data = [
            {
                "display_id": a.display_id,
                "title": a.title,
                "severity": a.severity,
                "source_kind": a.source_kind,
                "state": a.state,
                "created_at": a.created_at.isoformat(),
                "agent_name": (a.source_ref or {}).get("agent_name"),
            }
            for a in alerts
        ]
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


class TaskListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskFilterSet
    serializer_class = TaskSerializer

    def get_queryset(self):
        visible_ids = filter_incidents_for_user(
            Incident.objects.all(), self.request.user
        ).values_list("id", flat=True)
        return (
            Task.objects
            .filter(incident_id__in=visible_ids)
            .select_related("incident", "assignee", "template_item__template")
        )

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        sort = self.request.query_params.get("sort", "")
        order = self.request.query_params.get("order", "")
        if sort in _TASK_SORT_FIELDS:
            field = _TASK_SORT_FIELDS[sort]
            if order == "asc":
                qs = qs.order_by(F(field).asc(nulls_last=True))
            else:
                qs = qs.order_by(F(field).desc(nulls_last=True))
        else:
            qs = qs.order_by("-created_at")
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
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
        results = qs[start: start + per_page]
        return Response({
            "count": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "results": self.get_serializer(results, many=True).data,
        })


class TaskDetailView(GenericAPIView):
    serializer_class = TaskSerializer

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
    @extend_schema(responses=TaskSerializer)
    def post(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.select_related("incident", "automation", "wazuh_response").get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, task.incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if task.task_type == Task.TYPE_WAZUH_RESPONSE:
            return _run_wazuh_response_task(request, task)

        if task.task_type != Task.TYPE_AUTOMATED:
            return Response({"detail": "Task is not of type automated."}, status=status.HTTP_400_BAD_REQUEST)
        if not task.automation_id:
            return Response({"detail": "Task has no automation attached."}, status=status.HTTP_400_BAD_REQUEST)

        from automations.semaphore import SemaphoreAPIError, SemaphoreClient

        extra_vars, err = _build_extra_vars(task)
        if err:
            # UnresolvableVarError — surface as 400 with "detail" key for run
            return Response({"detail": err.data["error"]}, status=status.HTTP_400_BAD_REQUEST)

        override_vars = request.data.get("vars")
        if isinstance(override_vars, dict):
            extra_vars.update(override_vars)

        try:
            client = SemaphoreClient()
            semaphore_task_id = client.launch_job(
                template_id=task.automation.semaphore_template_id,
                extra_vars=extra_vars,
            )
        except SemaphoreAPIError as exc:
            logger.exception(
                "launch_job failed for task=%s automation=%s template_id=%s: status=%s extra_vars=%s",
                task.pk,
                task.automation_id,
                task.automation.semaphore_template_id,
                exc.status_code,
                extra_vars,
            )
            return Response({"detail": "Service error launching automation."}, status=status.HTTP_502_BAD_GATEWAY)

        update_fields = dict(
            semaphore_task_id=semaphore_task_id,
            state=Task.STATE_IN_PROGRESS,
            automation_error=None,
        )
        if not task.assignee_id:
            update_fields["assignee"] = request.user
        Task.objects.filter(pk=task.pk).update(**update_fields)
        task.refresh_from_db()
        return Response(TaskSerializer(task).data)


def _run_wazuh_response_task(request, task):
    from automations.interpolation import interpolate_args
    from security.wazuh import WazuhAPIError, WazuhClient

    if not task.wazuh_response_id:
        return Response({"detail": "Task has no Wazuh response attached."}, status=status.HTTP_400_BAD_REQUEST)

    wr = task.wazuh_response
    incident = Incident.objects.prefetch_related("assets", "iocs").get(pk=task.incident_id)

    # Resolve args
    override_args = (request.data.get("args") or "").strip()
    resolved_args = override_args if override_args else interpolate_args(wr.default_args, incident)

    # Determine agent IDs to target
    agent_ids_raw = request.data.get("agent_ids")
    if agent_ids_raw and isinstance(agent_ids_raw, list):
        agent_ids = [str(a) for a in agent_ids_raw]
    else:
        # Fall back to all assets with agent names linked to this incident
        agent_ids = list(
            incident.assets.filter(agent_name__isnull=False).values_list("agent_name", flat=True)
        )

    timeout_override = request.data.get("timeout")
    timeout = int(timeout_override) if timeout_override is not None else wr.timeout

    wazuh_status_code = None
    wazuh_response_body = {}
    error_msg = None

    try:
        client = WazuhClient()
        wazuh_status_code, wazuh_response_body = client.run_active_response(
            command=wr.command,
            agent_ids=agent_ids,
            args=resolved_args,
            timeout=timeout,
        )
    except WazuhAPIError as exc:
        logger.exception("WazuhAPIError running active response task=%s", task.pk)
        error_msg = str(exc)

    with transaction.atomic():
        Task.objects.filter(pk=task.pk).update(
            state=Task.STATE_DONE,
            automation_error=error_msg,
            assignee=task.assignee or request.user,
        )
        task.refresh_from_db()

        execution = WazuhResponseExecution.objects.create(
            wazuh_response=wr,
            executed_by=request.user,
            agent_ids=agent_ids,
            resolved_args=resolved_args,
            timeout_used=timeout,
            incident=task.incident,
            task=task,
            wazuh_status_code=wazuh_status_code,
            wazuh_response_body=wazuh_response_body,
        )

        agents_str = ", ".join(agent_ids) if agent_ids else "no agents"
        if error_msg:
            body = (
                f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to {agents_str} "
                f"by {request.user.username}. **Error:** {error_msg}"
            )
        else:
            body = (
                f"Wazuh active response **{wr.name}** (`{wr.command}`) dispatched to {agents_str} "
                f"by {request.user.username}. Status {wazuh_status_code} — dispatch confirmed "
                f"(not execution confirmed)."
            )
        Comment.objects.create(
            incident=task.incident,
            author=request.user,
            body=body,
            kind=Comment.KIND_SYSTEM,
        )
        record_event(
            task.incident,
            "wazuh_response_dispatched",
            actor=request.user,
            payload={
                "task_id": task.id,
                "wazuh_response_id": wr.id,
                "wazuh_response_name": wr.name,
                "command": wr.command,
                "agent_ids": agent_ids,
                "resolved_args": resolved_args,
                "timeout_used": timeout,
                "execution_id": execution.id,
                "status_code": wazuh_status_code,
                "error": error_msg,
            },
        )

    return Response(TaskSerializer(task).data)


def _build_extra_vars(task):
    """Merge default_vars + resolved mappings + hardcoded incident fields.

    Returns (vars_dict, error_response) — exactly one of the two is None.
    """
    from automations.incident_vars import UnresolvableVarError, resolve_incident_vars
    import yaml

    incident = task.incident

    extra_vars = {}
    if task.automation.default_vars:
        parsed = yaml.safe_load(task.automation.default_vars)
        if isinstance(parsed, dict):
            extra_vars.update(parsed)

    if task.automation.incident_var_mappings:
        incident = Incident.objects.prefetch_related("assets", "iocs").get(pk=incident.pk)
        try:
            extra_vars.update(resolve_incident_vars(task.automation.incident_var_mappings, incident))
        except UnresolvableVarError as exc:
            return None, Response(
                {"error": f"Mapping for '{exc.var_name}' (source: {exc.source}) resolved to no values."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    extra_vars.update({
        "incident_id": incident.id,
        "incident_display_id": incident.display_id,
        "incident_title": incident.title,
        "incident_severity": incident.severity,
    })
    return extra_vars, None


class TaskPreviewView(APIView):
    def get(self, request, pk):
        err = _require_auth(request)
        if err:
            return err
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            task = Task.objects.select_related("incident", "automation", "wazuh_response").get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_incident(request.user, task.incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if task.task_type == Task.TYPE_WAZUH_RESPONSE:
            if not task.wazuh_response_id:
                return Response({"detail": "Task has no Wazuh response attached."}, status=status.HTTP_400_BAD_REQUEST)
            from automations.interpolation import interpolate_args
            from security.models import OrganizationMembership
            wr = task.wazuh_response
            incident = Incident.objects.prefetch_related("assets", "iocs").get(pk=task.incident_id)
            resolved_args = interpolate_args(wr.default_args, incident)
            eligible_agents = list(
                incident.assets.filter(
                    agent_name__isnull=False
                ).values("id", "name", "agent_name", "ip_address")
            )
            return Response({
                "resolved_args": resolved_args,
                "eligible_agents": eligible_agents,
                "timeout": wr.timeout,
                "requires_confirmation": wr.requires_confirmation,
                "command": wr.command,
            })

        if task.task_type != Task.TYPE_AUTOMATED:
            return Response({"detail": "Task is not of type automated."}, status=status.HTTP_400_BAD_REQUEST)
        if not task.automation_id:
            return Response({"detail": "Task has no automation attached."}, status=status.HTTP_400_BAD_REQUEST)

        extra_vars, err = _build_extra_vars(task)
        if err:
            return err
        return Response({"vars": extra_vars})


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
            link_source_assets(incident, org)
            extract_and_save_iocs(incident)
            record_event(incident, "incident_created", actor=request.user)
            if acquire_triage_lock(incident.id):
                incident_id = incident.id
                transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))

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


class TaskCommentListView(GenericAPIView):
    serializer_class = CommentSerializer

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
            logger.exception("Error generating upload URL for incident=%s filename=%s", incident.display_id, filename)
            return Response({"detail": "Internal error processing attachment."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            logger.exception("Error confirming upload for attachment=%s", attachment_id)
            return Response({"detail": "Internal error confirming upload."}, status=status.HTTP_400_BAD_REQUEST)

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
            logger.exception("Error generating download URL for attachment=%s", attachment_id)
            return Response({"detail": "Internal error generating download link."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            logger.exception("Error deleting attachment=%s", attachment_id)
            return Response({"detail": "Internal error deleting attachment."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentTriageView(APIView):
    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related("organization").get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not acquire_triage_lock(incident.id):
            return Response(
                {"detail": "Triage already in progress for this incident."},
                status=status.HTTP_409_CONFLICT,
            )

        run_incident_triage.delay(incident.id)
        return Response(status=status.HTTP_202_ACCEPTED)


class IncidentTriageDebugView(APIView):
    """
    GET  /api/incidents/<display_id>/triage/debug/  — return the prompts without running the LLM
    POST /api/incidents/<display_id>/triage/debug/  — run LLM with optional prompt overrides
    """

    def _get_incident(self, request, display_id):
        if not request.user.is_authenticated:
            return None, Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.is_staff:
            return None, Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            incident = Incident.objects.select_related("organization").prefetch_related(
                "incident_assets__asset", "iocs"
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
        from incidents.tasks import build_triage_prompts
        system_prompt, user_payload = build_triage_prompts(incident)
        return Response({"system_prompt": system_prompt, "user_payload": user_payload})

    def post(self, request, display_id):
        incident, err = self._get_incident(request, display_id)
        if err:
            return err
        from incidents.tasks import build_triage_prompts
        from incidents.llm.factory import get_triage_provider
        from incidents.llm.base import TriageConfigError, TriageError

        default_system, default_payload = build_triage_prompts(incident)
        system_prompt = request.data.get("system_prompt") or default_system
        user_payload = request.data.get("user_payload") or default_payload

        try:
            provider = get_triage_provider()
        except TriageConfigError as exc:
            return Response({"detail": f"LLM provider misconfigured: {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not hasattr(provider, "debug_triage_incident"):
            return Response({"detail": "This provider does not support debug mode."}, status=status.HTTP_501_NOT_IMPLEMENTED)

        try:
            raw_response, parsed = provider.debug_triage_incident(system_prompt, user_payload)
        except TriageError as exc:
            return Response({"detail": f"LLM error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.exception("IncidentTriageDebugView: unexpected error for %s", display_id)
            return Response({"detail": f"Unexpected error: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "raw_response": raw_response,
            "result": parsed,
        })


# ── Incident assistant ─────────────────────────────────────────────────────────

class IncidentAssistantView(APIView):
    """Staff-only: multi-turn conversational assistant grounded in a specific incident.

    Stateless endpoint: accepts messages[] and recomputes grounding server-side every turn.
    Returns an assistant reply plus an allowlisted set of proposed actions for human confirmation.
    """

    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.select_related(
                "organization", "subject", "assignee"
            ).prefetch_related(
                "incident_assets__asset", "iocs", "tasks__assignee"
            ).get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        messages = request.data.get("messages") or []
        if not messages:
            return Response({"detail": "messages is required."}, status=status.HTTP_400_BAD_REQUEST)

        from incidents.llm.grounding import build_incident_grounding
        from incidents.llm.factory import get_assistant_provider
        from incidents.llm.base import AssistantConfigError, AssistantError, TriageConfigError

        grounding = build_incident_grounding(incident)

        try:
            provider = get_assistant_provider()
        except (AssistantConfigError, TriageConfigError) as exc:
            return Response(
                {"detail": "Incident assistant is unavailable.", "reason": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            result = provider.assist_incident(messages, grounding)
        except (AssistantConfigError, TriageConfigError) as exc:
            return Response(
                {"detail": "Incident assistant is unavailable.", "reason": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantError as exc:
            logger.warning("IncidentAssistantView: provider error: %s", exc)
            return Response(
                {"detail": "Assistant failed to produce a valid response.", "reason": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        proposed_actions = [
            {"type": a.type, "label": a.label, "payload": a.payload}
            for a in result.proposed_actions
        ]

        return Response({
            "assistant_reply": result.assistant_reply,
            "proposed_actions": proposed_actions,
            "warnings": result.warnings,
        })


class IncidentAssistantConfirmView(APIView):
    """Staff-only: record an audit timeline event when a user confirms an assistant-proposed action.

    Called by the frontend after the actual mutation endpoint succeeds, purely for audit.
    Does not mutate incident data itself.
    """

    def post(self, request, display_id):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_incident(request.user, incident):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        action_type = request.data.get("action_type")
        action_label = request.data.get("action_label", "")
        if not action_type:
            return Response({"detail": "action_type is required."}, status=status.HTTP_400_BAD_REQUEST)

        record_event(
            incident,
            "assistant_action",
            actor=request.user,
            payload={"action_type": action_type, "label": action_label},
        )
        return Response({"recorded": True})
