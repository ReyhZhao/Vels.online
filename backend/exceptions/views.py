import logging
from dataclasses import asdict

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from incidents.services.events import record_event
from security.models import OrganizationMembership

from .llm.factory import get_llm_provider
from .models import ExceptionRule
from .serializers import ExceptionRuleSerializer
from .services import allocate_rule_id, free_rule_id
from .services_github import push_rule, remove_rule

logger = logging.getLogger(__name__)


class ExceptionRuleListView(APIView):
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        # Resolve organisation
        org_slug = request.data.get("org")
        if not org_slug:
            return Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)
        from security.models import Organization
        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organisation not found."}, status=status.HTTP_404_NOT_FOUND)

        # Resolve optional incident FK
        incident = None
        incident_display_id = request.data.get("incident")
        if incident_display_id:
            try:
                incident = Incident.objects.get(display_id=incident_display_id)
            except Incident.DoesNotExist:
                return Response({"detail": "Incident not found."}, status=status.HTTP_404_NOT_FOUND)

        rule = ExceptionRule.objects.create(
            trigger_rule_id=request.data.get("trigger_rule_id") or None,
            description=request.data.get("description", ""),
            match_value=request.data.get("match_value") or "",
            field_name=request.data.get("field_name") or "",
            field_value=request.data.get("field_value") or "",
            field_type=request.data.get("field_type") or "",
            scope=request.data.get("scope", "org"),
            agent_name=request.data.get("agent_name") or "",
            organisation=org,
            incident=incident,
            created_by=request.user,
            status="applied",
            wazuh_rule_id=allocate_rule_id(),
        )

        if incident:
            record_event(
                incident,
                "exception_created",
                actor=request.user,
                payload={"rule_id": rule.id, "wazuh_rule_id": rule.wazuh_rule_id, "description": rule.description},
            )

        try:
            push_rule(rule)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("GitHub push failed for rule %s: %s", rule.id, exc)

        return Response(ExceptionRuleSerializer(rule).data, status=status.HTTP_201_CREATED)

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

        incident_filter = request.query_params.get("incident")
        if incident_filter:
            qs = qs.filter(incident__display_id=incident_filter)

        return Response(ExceptionRuleSerializer(qs, many=True).data)


class ExceptionRuleDetailView(APIView):
    def _get_rule(self, request, pk):
        try:
            rule = ExceptionRule.objects.select_related(
                "organisation", "incident", "created_by"
            ).get(pk=pk)
        except ExceptionRule.DoesNotExist:
            return None, Response({"detail": "Not found."}, status=404)

        if not request.user.is_staff:
            member_org_ids = OrganizationMembership.objects.filter(
                user=request.user
            ).values_list("organization_id", flat=True)
            if rule.organisation_id not in member_org_ids:
                return None, Response({"detail": "Not found."}, status=404)

        return rule, None

    def get(self, request, pk):
        rule, err = self._get_rule(request, pk)
        if err:
            return err
        return Response(ExceptionRuleSerializer(rule).data)

    def patch(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        rule, err = self._get_rule(request, pk)
        if err:
            return err

        EDITABLE = ("description", "match_value", "field_name", "field_value", "field_type", "agent_name", "scope")
        for field in EDITABLE:
            if field in request.data:
                setattr(rule, field, request.data[field])

        if "trigger_rule_id" in request.data:
            rule.trigger_rule_id = request.data["trigger_rule_id"] or None

        if rule.status == "applied":
            rule.status = "pending"

        rule.save()
        return Response(ExceptionRuleSerializer(rule).data)


class ExceptionApproveView(APIView):
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            rule = ExceptionRule.objects.get(pk=pk)
        except ExceptionRule.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        if rule.status != "pending":
            return Response({"detail": "Rule must be in pending status."}, status=status.HTTP_400_BAD_REQUEST)

        rule.status = "applied"
        rule.save(update_fields=["status"])

        try:
            push_rule(rule)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("GitHub push failed for rule %s: %s", rule.id, exc)

        return Response(ExceptionRuleSerializer(rule).data)


class ExceptionDisableView(APIView):
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        try:
            rule = ExceptionRule.objects.get(pk=pk)
        except ExceptionRule.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        if rule.status != "applied":
            return Response({"detail": "Rule must be in applied status."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            remove_rule(rule)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("GitHub remove failed for rule %s: %s", rule.id, exc)

        free_rule_id(rule.wazuh_rule_id)
        rule.status = "disabled"
        rule.save(update_fields=["status"])

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

        if not incident.source_ref:
            return Response(
                {"detail": "This incident has no Wazuh alert data attached. Cannot generate an exception proposal."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider = get_llm_provider()
            fields = provider.generate_exception(incident.source_ref)
        except Exception as exc:
            logger.exception("LLM provider error during exception generation for %s", incident.display_id)
            return Response({"detail": f"LLM provider error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(asdict(fields))
