import logging

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import AutomationFilterSet
from .models import Automation, WazuhActiveResponse
from .semaphore import SemaphoreAPIError, SemaphoreClient
from .serializers import AutomationSerializer

logger = logging.getLogger(__name__)


class AutomationListView(ListAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AutomationFilterSet
    serializer_class = AutomationSerializer

    def get_queryset(self):
        include_archived = self.request.query_params.get("include_archived") == "1"
        return Automation.objects.all() if include_archived else Automation.objects.filter(archived=False)

    def post(self, request):
        errors = {}
        name = (request.data.get("name") or "").strip()
        if not name:
            errors["name"] = "This field is required."
        template_id = request.data.get("semaphore_template_id")
        if template_id is None:
            errors["semaphore_template_id"] = "This field is required."
        if errors:
            return Response({"detail": errors}, status=400)

        automation = Automation.objects.create(
            name=name,
            semaphore_template_id=int(template_id),
            semaphore_template_name=(request.data.get("semaphore_template_name") or "").strip(),
            default_vars=request.data.get("default_vars") or None,
            incident_var_mappings=request.data.get("incident_var_mappings") or None,
            created_by=request.user,
        )
        return Response(_serialize(automation), status=201)


class AutomationDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        automation = get_object_or_404(Automation, pk=pk)
        update_fields = []
        if "name" in request.data:
            automation.name = (request.data["name"] or "").strip()
            update_fields.append("name")
        if "semaphore_template_id" in request.data:
            automation.semaphore_template_id = int(request.data["semaphore_template_id"])
            update_fields.append("semaphore_template_id")
        if "semaphore_template_name" in request.data:
            automation.semaphore_template_name = (request.data["semaphore_template_name"] or "").strip()
            update_fields.append("semaphore_template_name")
        if "default_vars" in request.data:
            automation.default_vars = request.data["default_vars"] or None
            update_fields.append("default_vars")
        if "incident_var_mappings" in request.data:
            automation.incident_var_mappings = request.data["incident_var_mappings"] or None
            update_fields.append("incident_var_mappings")
        if "archived" in request.data:
            automation.archived = bool(request.data["archived"])
            update_fields.append("archived")
        if update_fields:
            update_fields.append("updated_at")
            automation.save(update_fields=update_fields)
        return Response(_serialize(automation))

    def delete(self, request, pk):
        automation = get_object_or_404(Automation, pk=pk)
        automation.archived = True
        automation.save(update_fields=["archived", "updated_at"])
        return Response(status=204)


class SemaphoreTemplatesView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            client = SemaphoreClient()
            templates = client.list_templates()
        except SemaphoreAPIError as exc:
            logger.exception("Semaphore error listing templates")
            return Response({"detail": "Service error contacting Semaphore."}, status=502)
        return Response(templates)


def _serialize(automation):
    return {
        "id": automation.pk,
        "name": automation.name,
        "semaphore_template_id": automation.semaphore_template_id,
        "semaphore_template_name": automation.semaphore_template_name,
        "default_vars": automation.default_vars,
        "incident_var_mappings": automation.incident_var_mappings,
        "archived": automation.archived,
        "created_by": automation.created_by_id,
        "created_at": automation.created_at.isoformat() if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() if automation.updated_at else None,
    }


def _serialize_wazuh_response(obj):
    return {
        "id": obj.pk,
        "name": obj.name,
        "command": obj.command,
        "platforms": obj.platforms,
        "default_args": obj.default_args,
        "timeout": obj.timeout,
        "available_in_security_overview": obj.available_in_security_overview,
        "requires_confirmation": obj.requires_confirmation,
        "autonomous_triage_approved": obj.autonomous_triage_approved,
        "archived": obj.archived,
        "created_by": obj.created_by_id,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


class WazuhResponseListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        include_archived = request.query_params.get("include_archived") == "1"
        qs = WazuhActiveResponse.objects.all() if include_archived else WazuhActiveResponse.objects.filter(archived=False)
        return Response([_serialize_wazuh_response(r) for r in qs])

    def post(self, request):
        errors = {}
        name = (request.data.get("name") or "").strip()
        if not name:
            errors["name"] = "This field is required."
        command = (request.data.get("command") or "").strip()
        if not command:
            errors["command"] = "This field is required."
        if errors:
            return Response({"detail": errors}, status=400)

        platforms = request.data.get("platforms") or []
        if not isinstance(platforms, list):
            platforms = []

        obj = WazuhActiveResponse.objects.create(
            name=name,
            command=command,
            platforms=platforms,
            default_args=(request.data.get("default_args") or "").strip(),
            timeout=int(request.data.get("timeout") or 0),
            available_in_security_overview=bool(request.data.get("available_in_security_overview", False)),
            requires_confirmation=bool(request.data.get("requires_confirmation", False)),
            autonomous_triage_approved=bool(request.data.get("autonomous_triage_approved", False)),
            created_by=request.user,
        )
        return Response(_serialize_wazuh_response(obj), status=201)


class WazuhResponseDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        obj = get_object_or_404(WazuhActiveResponse, pk=pk)
        update_fields = []
        for field in ["name", "command", "default_args"]:
            if field in request.data:
                setattr(obj, field, (request.data[field] or "").strip())
                update_fields.append(field)
        if "platforms" in request.data:
            obj.platforms = request.data["platforms"] if isinstance(request.data["platforms"], list) else []
            update_fields.append("platforms")
        if "timeout" in request.data:
            obj.timeout = int(request.data["timeout"] or 0)
            update_fields.append("timeout")
        for bool_field in ["available_in_security_overview", "requires_confirmation", "autonomous_triage_approved", "archived"]:
            if bool_field in request.data:
                setattr(obj, bool_field, bool(request.data[bool_field]))
                update_fields.append(bool_field)
        if update_fields:
            update_fields.append("updated_at")
            obj.save(update_fields=update_fields)
        return Response(_serialize_wazuh_response(obj))

    def delete(self, request, pk):
        obj = get_object_or_404(WazuhActiveResponse, pk=pk)
        obj.archived = True
        obj.save(update_fields=["archived", "updated_at"])
        return Response(status=204)
