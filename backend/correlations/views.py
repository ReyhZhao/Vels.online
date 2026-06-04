import logging

from rest_framework import serializers as _s
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .models import (
    ALERT_FIELD_CATALOG,
    ENTITY_CATALOG,
    FIELD_KIND_ALERT,
    FIELD_KIND_ENTITY,
    FIELD_KIND_SOURCE_REF,
    OPERATOR_CHOICES,
    OPERATOR_CIDR,
    OPERATOR_GTE,
    OPERATOR_LTE,
    SOURCE_REF_CATALOG,
    CorrelationRule,
    CorrelationRuleLeg,
    DetectionSuggestion,
    LegCondition,
)
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


# ── Field catalog ─────────────────────────────────────────────────────────────

_ALLOWED_OPERATORS = {
    FIELD_KIND_ALERT: {"equals", "in", "contains", "gte", "lte"},
    FIELD_KIND_ENTITY: {"equals", "in", "contains", "cidr"},
    FIELD_KIND_SOURCE_REF: {"equals", "in", "contains"},
}

_FIELD_CATALOG = {
    FIELD_KIND_ALERT: sorted(ALERT_FIELD_CATALOG),
    FIELD_KIND_ENTITY: sorted(ENTITY_CATALOG),
    FIELD_KIND_SOURCE_REF: sorted(SOURCE_REF_CATALOG),
}

_OPERATOR_LABELS = dict(OPERATOR_CHOICES)


class CorrelationCatalogView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            "fields": {
                kind: [{"value": f, "label": f} for f in fields]
                for kind, fields in _FIELD_CATALOG.items()
            },
            "operators": {
                kind: [{"value": op, "label": _OPERATOR_LABELS[op]} for op in sorted(ops)]
                for kind, ops in _ALLOWED_OPERATORS.items()
            },
            "field_kinds": [
                {"value": FIELD_KIND_ALERT, "label": "Alert field"},
                {"value": FIELD_KIND_ENTITY, "label": "ECS entity"},
                {"value": FIELD_KIND_SOURCE_REF, "label": "Source ref key"},
            ],
            "correlation_keys": [
                {"value": "none", "label": "None (org-wide)"},
                {"value": "host.name", "label": "Host (host.name)"},
                {"value": "source.ip", "label": "Source IP (source.ip)"},
                {"value": "user.name", "label": "Username (user.name)"},
                {"value": "file.hash.sha256", "label": "File Hash (file.hash.sha256)"},
                {"value": "process.name", "label": "Process (process.name)"},
            ],
            "severities": ["critical", "high", "medium", "low", "info"],
        })


# ── CRUD serializers ──────────────────────────────────────────────────────────

class _LegConditionSerializer(_s.ModelSerializer):
    class Meta:
        model = LegCondition
        fields = ["id", "field_kind", "field_name", "operator", "value"]

    def validate(self, data):
        field_kind = data.get("field_kind")
        field_name = data.get("field_name")
        operator = data.get("operator")

        catalog = _FIELD_CATALOG.get(field_kind, set())
        if field_name not in catalog:
            raise _s.ValidationError(
                {"field_name": f"'{field_name}' is not a valid field for kind '{field_kind}'."}
            )

        allowed_ops = _ALLOWED_OPERATORS.get(field_kind, set())
        if operator not in allowed_ops:
            raise _s.ValidationError(
                {"operator": f"'{operator}' is not allowed for field kind '{field_kind}'."}
            )

        return data


class _LegSerializer(_s.ModelSerializer):
    conditions = _LegConditionSerializer(many=True)

    class Meta:
        model = CorrelationRuleLeg
        fields = ["id", "count", "display_order", "conditions"]


class _CorrelationRuleSerializer(_s.ModelSerializer):
    legs = _LegSerializer(many=True)

    class Meta:
        model = CorrelationRule
        fields = [
            "id", "organization", "name", "description",
            "correlation_key", "window_minutes", "severity",
            "enabled", "created_at", "updated_at", "legs",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _create_legs(self, rule, legs_data):
        for leg_data in legs_data:
            conditions_data = leg_data.pop("conditions", [])
            leg = CorrelationRuleLeg.objects.create(rule=rule, **leg_data)
            for cond_data in conditions_data:
                LegCondition.objects.create(leg=leg, **cond_data)

    def create(self, validated_data):
        legs_data = validated_data.pop("legs", [])
        rule = CorrelationRule.objects.create(**validated_data)
        self._create_legs(rule, legs_data)
        return rule

    def update(self, instance, validated_data):
        legs_data = validated_data.pop("legs", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if legs_data is not None:
            instance.legs.all().delete()
            self._create_legs(instance, legs_data)
        return instance


# ── CRUD views ────────────────────────────────────────────────────────────────

def _require_staff(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)
    if not request.user.is_staff:
        return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
    return None


class CorrelationRuleListView(APIView):
    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        rules = (
            CorrelationRule.objects
            .prefetch_related("legs__conditions")
            .order_by("name")
        )
        return Response(_CorrelationRuleSerializer(rules, many=True).data)

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err
        serializer = _CorrelationRuleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        rule = serializer.save()
        rule.refresh_from_db()
        rule.legs.prefetch_related("conditions")
        return Response(
            _CorrelationRuleSerializer(
                CorrelationRule.objects.prefetch_related("legs__conditions").get(pk=rule.pk)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class CorrelationRuleDetailView(APIView):
    def _get_rule(self, pk):
        try:
            return CorrelationRule.objects.prefetch_related("legs__conditions").get(pk=pk)
        except CorrelationRule.DoesNotExist:
            return None

    def get(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = self._get_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_CorrelationRuleSerializer(rule).data)

    def patch(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = self._get_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = _CorrelationRuleSerializer(rule, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(
            _CorrelationRuleSerializer(
                CorrelationRule.objects.prefetch_related("legs__conditions").get(pk=pk)
            ).data
        )

    def delete(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = self._get_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
