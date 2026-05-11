from dataclasses import asdict

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from security.models import OrganizationMembership

from .llm.factory import get_llm_provider
from .models import ExceptionRule
from .serializers import ExceptionRuleSerializer


class ExceptionRuleListView(APIView):
    def get(self, request):
        if request.user.is_staff:
            qs = ExceptionRule.objects.select_related("organisation", "incident", "created_by")
        else:
            member_org_ids = OrganizationMembership.objects.filter(
                user=request.user
            ).values_list("organization_id", flat=True)
            qs = ExceptionRule.objects.select_related(
                "organisation", "incident", "created_by"
            ).filter(organisation_id__in=member_org_ids)

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        org_filter = request.query_params.get("organisation")
        if org_filter:
            qs = qs.filter(organisation__slug=org_filter)

        return Response(ExceptionRuleSerializer(qs, many=True).data)


class ExceptionRuleDetailView(APIView):
    def get(self, request, pk):
        try:
            rule = ExceptionRule.objects.select_related(
                "organisation", "incident", "created_by"
            ).get(pk=pk)
        except ExceptionRule.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        if not request.user.is_staff:
            member_org_ids = OrganizationMembership.objects.filter(
                user=request.user
            ).values_list("organization_id", flat=True)
            if rule.organisation_id not in member_org_ids:
                return Response({"detail": "Not found."}, status=404)

        return Response(ExceptionRuleSerializer(rule).data)


class ExceptionGenerateView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        display_id = request.data.get("display_id")
        if not display_id:
            return Response({"detail": "display_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            incident = Incident.objects.get(display_id=display_id)
        except Incident.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if incident.source_kind != Incident.SOURCE_WAZUH_EVENT:
            return Response(
                {"detail": "Incident must have source_kind 'wazuh_event'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider = get_llm_provider()
        try:
            fields = provider.generate_exception(incident.source_ref)
        except Exception as exc:
            return Response({"detail": f"LLM provider error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(asdict(fields))
