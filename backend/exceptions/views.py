from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import OrganizationMembership

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
