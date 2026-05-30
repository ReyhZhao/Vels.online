import logging
import re
from dataclasses import asdict

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.models import Incident
from incidents.services.events import record_event
from security.models import OrganizationMembership

from .filters import ExceptionRuleFilterSet
from .llm.factory import get_llm_provider
from .models import ExceptionRule
from .serializers import ExceptionRuleSerializer
from .services import allocate_rule_id, free_rule_id
from .services_github import push_rule, remove_rule

logger = logging.getLogger(__name__)

_ANGLE_BRACKET_RE = re.compile(r"<[^<>]+>")
_SQUARE_BRACKET_RE = re.compile(r"\[[^[\]]+\]")
_ALL_CAPS_UNDERSCORE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def _is_placeholder(value: str) -> bool:
    """Return True when *value* looks like a template placeholder rather than real data."""
    if not value:
        return False
    if _ANGLE_BRACKET_RE.search(value):
        return True
    if _SQUARE_BRACKET_RE.search(value):
        return True
    if _ALL_CAPS_UNDERSCORE_RE.match(value.strip()):
        return True
    return False


class ExceptionRuleListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = ExceptionRuleFilterSet
    serializer_class = ExceptionRuleSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return ExceptionRule.objects.select_related("organisation", "incident", "created_by")
        member_org_ids = OrganizationMembership.objects.filter(
            user=self.request.user
        ).values_list("organization_id", flat=True)
        return ExceptionRule.objects.select_related(
            "organisation", "incident", "created_by"
        ).filter(organisation_id__in=member_org_ids)

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

        # Validate trigger_rule_id
        trigger_rule_id_raw = request.data.get("trigger_rule_id")
        if not trigger_rule_id_raw:
            return Response(
                {"detail": "trigger_rule_id is required and must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            trigger_rule_id = int(trigger_rule_id_raw)
            if trigger_rule_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "trigger_rule_id must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate description
        description = request.data.get("description", "").strip()
        if not description:
            return Response(
                {"detail": "description is required and must not be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Detect placeholder values in string fields
        string_fields = {
            "description": description,
            "match_value": request.data.get("match_value") or "",
            "field_name": request.data.get("field_name") or "",
            "field_value": request.data.get("field_value") or "",
            "agent_name": request.data.get("agent_name") or "",
        }
        for field_name, field_val in string_fields.items():
            if _is_placeholder(field_val):
                return Response(
                    {"detail": f"'{field_name}' contains a placeholder value and cannot be saved."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Resolve optional incident FK
        incident = None
        incident_display_id = request.data.get("incident")
        if incident_display_id:
            try:
                incident = Incident.objects.get(display_id=incident_display_id)
            except Incident.DoesNotExist:
                return Response({"detail": "Incident not found."}, status=status.HTTP_404_NOT_FOUND)

        rule = ExceptionRule.objects.create(
            trigger_rule_id=trigger_rule_id,
            description=description,
            match_value=string_fields["match_value"],
            field_name=string_fields["field_name"],
            field_value=string_fields["field_value"],
            field_type=request.data.get("field_type") or "",
            scope=request.data.get("scope", "org"),
            agent_name=string_fields["agent_name"],
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
            logger.error("GitHub push failed for rule %s: %s", rule.id, exc)
            free_rule_id(rule.wazuh_rule_id)
            rule.delete()
            return Response(
                {"detail": f"Exception rule saved but could not be pushed to GitHub: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(ExceptionRuleSerializer(rule).data, status=status.HTTP_201_CREATED)



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

        try:
            push_rule(rule)
        except Exception as exc:
            logger.error("GitHub push failed for rule %s: %s", rule.id, exc)
            return Response(
                {"detail": f"Could not push exception rule to GitHub: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        rule.status = "applied"
        rule.save(update_fields=["status"])

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
            logger.error("GitHub remove failed for rule %s: %s", rule.id, exc)
            return Response(
                {"detail": f"Could not remove exception rule from GitHub: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

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
            return Response({"detail": "LLM provider error. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(asdict(fields))
