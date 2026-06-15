import logging

from django.db.models import Count, Max
from rest_framework import serializers as _s
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .llm.base import DraftConfigError, DraftError
from .llm.factory import get_draft_provider
from .llm.grounding import build_grounding
from .llm.sanitizer import sanitize_draft
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
    SEARCH_COUNT_OP_CHOICES,
    SEARCH_COUNT_OP_LTE,
    SEARCH_OPERATOR_CHOICES,
    SOURCE_REF_CATALOG,
    CorrelationRule,
    CorrelationRuleLeg,
    DetectionSuggestion,
    LegCondition,
    SearchRule,
    SearchRuleLeg,
    SearchLegCondition,
    SearchRuleMute,
    SearchRuleTest,
    SystemRuleMute,
)
from .tasks import _create_incident_from_suggestion, run_scheduled_search_rule

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
            "search_operators": [
                {"value": v, "label": l} for v, l in SEARCH_OPERATOR_CHOICES
            ],
            "count_operators": [
                {"value": v, "label": l} for v, l in SEARCH_COUNT_OP_CHOICES
            ],
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


# ── Per-org system rule mute views ────────────────────────────────────────────

def _get_org_for_staff(request):
    org_slug = request.query_params.get("org") or request.data.get("org")
    if not org_slug:
        return None, Response({"detail": "org is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        return Organization.objects.get(slug=org_slug), None
    except Organization.DoesNotExist:
        return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class OrgSystemRulesView(APIView):
    """List system rules with per-org mute status. Staff only."""

    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        org, err = _get_org_for_staff(request)
        if err:
            return err

        system_rules = (
            CorrelationRule.objects
            .filter(organization=None)
            .prefetch_related("legs__conditions")
            .order_by("name")
        )
        muted_ids = set(
            SystemRuleMute.objects.filter(organization=org).values_list("rule_id", flat=True)
        )
        data = []
        for rule in system_rules:
            row = _CorrelationRuleSerializer(rule).data
            row["muted"] = rule.id in muted_ids
            data.append(row)
        return Response(data)


class OrgSystemRuleMuteView(APIView):
    """Create or remove a mute record for a system rule + org pair. Staff only."""

    def _resolve(self, request, pk):
        err = _require_staff(request)
        if err:
            return None, None, err
        org, err = _get_org_for_staff(request)
        if err:
            return None, None, err
        try:
            rule = CorrelationRule.objects.get(pk=pk, organization=None)
        except CorrelationRule.DoesNotExist:
            return None, None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return rule, org, None

    def post(self, request, pk):
        rule, org, err = self._resolve(request, pk)
        if err:
            return err
        SystemRuleMute.objects.get_or_create(organization=org, rule=rule)
        return Response({"rule_id": rule.id, "muted": True})

    def delete(self, request, pk):
        rule, org, err = self._resolve(request, pk)
        if err:
            return err
        SystemRuleMute.objects.filter(organization=org, rule=rule).delete()
        return Response({"rule_id": rule.id, "muted": False})


# ── Rule-author assistant ─────────────────────────────────────────────────────

class CorrelationDraftView(APIView):
    """Staff-only: given a conversation and optional current draft, return an LLM-drafted rule."""

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err

        messages = request.data.get("messages") or []
        if not messages:
            return Response({"detail": "messages is required."}, status=status.HTTP_400_BAD_REQUEST)

        current_draft = request.data.get("current_draft") or None
        scope = request.data.get("scope")

        # Validate scope and derive ownership server-side — never trust org from client
        org_for_draft = None
        if scope and scope != "all":
            try:
                org_for_draft = Organization.objects.get(slug=scope)
            except Organization.DoesNotExist:
                return Response({"detail": "Unknown scope."}, status=status.HTTP_400_BAD_REQUEST)

        grounding = build_grounding(scope=scope)

        try:
            provider = get_draft_provider()
        except DraftConfigError as exc:
            logger.exception("CorrelationDraftView: provider config error")
            return Response(
                {"detail": "Rule-author assistant is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            result = provider.draft_rule(messages, grounding, current_draft)
        except DraftConfigError as exc:
            logger.exception("CorrelationDraftView: provider config error during draft")
            return Response(
                {"detail": "Rule-author assistant is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except DraftError as exc:
            logger.warning("CorrelationDraftView: provider error: %s", exc)
            return Response(
                {"detail": "Assistant failed to produce a valid draft."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        sanitized, sanitizer_warnings = sanitize_draft(result.updated_draft)

        # Inject ownership default derived from scope
        sanitized["organization"] = org_for_draft.pk if org_for_draft else None

        return Response({
            "updated_draft": sanitized,
            "assistant_reply": result.assistant_reply,
            "warnings": result.warnings + sanitizer_warnings,
        })


# ── Search Rule author assistant ─────────────────────────────────────────────

class SearchRuleDraftView(APIView):
    """Staff-only: two-pass search rule drafter (ADR-0007).

    Pass 1 — provider selects relevant rule.ids from the cached catalog.
    Pass 2 — provider drafts a SearchRule using lazily-expanded fields for those ids.
    Endpoint is a pure function of {scope, messages[], current_draft}; nothing is persisted.
    """

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err

        messages = request.data.get("messages") or []
        if not messages:
            return Response({"detail": "messages is required."}, status=status.HTTP_400_BAD_REQUEST)

        current_draft = request.data.get("current_draft") or None
        scope = request.data.get("scope")

        org_for_draft = None
        agent_ids = None
        if scope and scope != "all":
            try:
                org_for_draft = Organization.objects.get(slug=scope)
            except Organization.DoesNotExist:
                return Response({"detail": "Unknown scope."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                from security.wazuh import WazuhClient, WazuhAPIError, WazuhAuthError
                raw_agents = WazuhClient().get_agents(org_for_draft.wazuh_group)
                agent_ids = [a["id"] for a in raw_agents]
            except Exception:
                agent_ids = []

        try:
            provider = get_draft_provider()
        except DraftConfigError as exc:
            logger.exception("SearchRuleDraftView: provider config error")
            return Response(
                {"detail": "Rule-author assistant is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        from .llm.search_grounding import build_search_grounding, expand_rule_fields
        from .llm.search_sanitizer import sanitize_search_draft

        grounding = build_search_grounding(scope=scope, agent_ids=agent_ids)

        # Phase 1 (research): let the model search the internet for threat
        # intelligence before drafting (ADR-0011). Ollama runs web_search as a tool;
        # Gemini does it via native grounding (handled in its own draft path).
        tool_trace = []
        try:
            from assistants.orchestrator import run_research_phase, research_notes, LoopCaps
            from assistants.web_search import build_web_search_tool, web_search_available

            uses_native = getattr(provider, "uses_native_web_search", lambda: False)()
            if web_search_available() and hasattr(provider, "chat") and not uses_native:
                research_sys = {
                    "role": "system",
                    "content": (
                        "You are helping author a detection rule. Use web_search to look up "
                        "threat intelligence that will help you draft an accurate rule. Search "
                        "only when it helps; stop once you have what you need."
                    ),
                }
                research = run_research_phase(
                    provider, [build_web_search_tool()], [research_sys] + messages,
                    LoopCaps.from_settings(),
                )
                grounding["research_notes"] = research_notes(research)
                tool_trace = research.tool_trace
        except Exception as exc:  # research is best-effort; never block drafting
            logger.warning("SearchRuleDraftView research phase error: %s", exc)

        try:
            # Pass 1: LLM selects relevant rule.ids from the catalog.
            selected_ids = provider.select_relevant_rule_ids(messages, grounding)
        except (DraftConfigError, DraftError) as exc:
            logger.warning("SearchRuleDraftView pass 1 error: %s", exc)
            selected_ids = []

        # Lazy field expansion for the selected rule.ids.
        expanded = expand_rule_fields(
            rule_ids=selected_ids,
            agent_ids=agent_ids,
            mapping=grounding.get("mapping", {}),
        )
        grounding["expanded_fields"] = expanded

        try:
            # Pass 2: LLM drafts the rule using expanded fields.
            result = provider.draft_search_rule(messages, grounding, current_draft)
        except DraftConfigError as exc:
            logger.exception("SearchRuleDraftView: provider config error during pass 2")
            return Response(
                {"detail": "Rule-author assistant is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except DraftError as exc:
            logger.warning("SearchRuleDraftView pass 2 error: %s", exc)
            return Response(
                {"detail": "Assistant failed to produce a valid draft."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        mapping = grounding.get("mapping", {})
        sanitized, sanitizer_warnings = sanitize_search_draft(result.updated_draft, mapping)
        sanitized["organization"] = org_for_draft.pk if org_for_draft else None

        return Response({
            "updated_draft": sanitized,
            "assistant_reply": result.assistant_reply,
            "warnings": result.warnings + sanitizer_warnings,
            "tool_trace": tool_trace,
        })


# ── Scheduled Search Rule CRUD ────────────────────────────────────────────────

# Curated core fields exposed in the search rule builder (friendly labels + expected types).
_SEARCH_CORE_FIELDS = [
    {"value": "rule.id",           "label": "Rule ID",          "type": "keyword"},
    {"value": "rule.level",        "label": "Rule Level",        "type": "long"},
    {"value": "rule.description",  "label": "Rule Description",  "type": "text"},
    {"value": "rule.groups",       "label": "Rule Groups",       "type": "keyword"},
    {"value": "agent.name",        "label": "Agent Name",        "type": "keyword"},
    {"value": "agent.id",          "label": "Agent ID",          "type": "keyword"},
    {"value": "data.srcip",        "label": "Source IP",         "type": "ip"},
    {"value": "data.dstip",        "label": "Destination IP",    "type": "ip"},
    {"value": "data.dstuser",      "label": "Destination User",  "type": "keyword"},
    {"value": "data.audit.comm",   "label": "Audit Command",     "type": "keyword"},
    {"value": "data.sha256",       "label": "File SHA256",       "type": "keyword"},
]


def _get_mapping_safe() -> dict:
    """Fetch the live field mapping; return {} on any error."""
    try:
        from security.opensearch import OpenSearchClient
        return OpenSearchClient().get_field_mapping()
    except Exception:
        logger.warning("SearchRule validation: could not fetch field mapping — skipping type check")
        return {}


class _SearchLegConditionSerializer(_s.ModelSerializer):
    class Meta:
        model = SearchLegCondition
        fields = ["id", "field_name", "operator", "value"]

    def validate(self, data):
        from correlations.services.search_compiler import validate_search_field
        field_name = data.get("field_name", "")
        operator = data.get("operator", "")
        mapping = _get_mapping_safe()
        ok, reason = validate_search_field(field_name, operator, mapping)
        if not ok:
            raise _s.ValidationError({"field_name": reason})
        return data


class _SearchRuleLegSerializer(_s.ModelSerializer):
    conditions = _SearchLegConditionSerializer(many=True)

    class Meta:
        model = SearchRuleLeg
        fields = [
            "id", "count", "count_operator", "display_order",
            "distinct_field", "min_distinct", "conditions",
        ]


def _compute_test_summary(tests) -> dict:
    """Aggregate last-run statuses across a rule's Rule Tests for the list-row badge."""
    tests = list(tests)
    return {
        "total": len(tests),
        "passing": sum(1 for t in tests if t.last_status == "pass"),
        "failing": sum(1 for t in tests if t.last_status == "fail"),
        "error": sum(1 for t in tests if t.last_status == "error"),
        "never": sum(1 for t in tests if t.last_status == "never"),
    }


class _SearchRuleSerializer(_s.ModelSerializer):
    legs = _SearchRuleLegSerializer(many=True)
    test_summary = _s.SerializerMethodField()
    firing_summary = _s.SerializerMethodField()
    # Time-of-day window (#440). Days are ISO weekdays 1=Mon … 7=Sun.
    time_window_start = _s.TimeField(required=False, allow_null=True)
    time_window_end = _s.TimeField(required=False, allow_null=True)
    time_window_days = _s.ListField(
        child=_s.IntegerField(min_value=1, max_value=7), required=False
    )

    class Meta:
        model = SearchRule
        fields = [
            "id", "organization", "name", "description",
            "severity", "correlation_key", "window_minutes", "interval_minutes",
            "max_findings_per_run", "include_agentless", "enabled", "created_at", "updated_at",
            "time_window_start", "time_window_end", "time_window_days", "time_window_mode",
            "legs", "test_summary", "firing_summary",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_test_summary(self, obj):
        return _compute_test_summary(obj.tests.all())

    def get_firing_summary(self, obj):
        """Per-rule firing count + last fired_at, derived from the SearchFiring ledger.

        Reads queryset annotations (`firing_count` / `last_fired_at`) when present so
        the list view computes both in a single aggregate (no N+1); falls back to an
        aggregate for detail/create responses that serialize a single rule.
        """
        count = getattr(obj, "firing_count", None)
        last = getattr(obj, "last_fired_at", None)
        if count is None:
            agg = obj.firings.aggregate(count=Count("id"), last=Max("fired_at"))
            count = agg["count"]
            last = agg["last"]
        return {
            "count": count or 0,
            "last_fired_at": last.isoformat() if last else None,
        }

    def validate_interval_minutes(self, value):
        from correlations.models import _MIN_INTERVAL_MINUTES
        if value < _MIN_INTERVAL_MINUTES:
            raise _s.ValidationError(
                f"interval_minutes must be at least {_MIN_INTERVAL_MINUTES}."
            )
        return value

    def validate_correlation_key(self, value):
        from correlations.models import CORRELATION_KEY_NONE
        from correlations.services.search_compiler import (
            CORRELATION_KEY_TO_WAZUH_FIELD,
            is_aggregatable_field,
        )
        if value == CORRELATION_KEY_NONE:
            return value
        wazuh_field = CORRELATION_KEY_TO_WAZUH_FIELD.get(value)
        if wazuh_field:
            mapping = _get_mapping_safe()
            if mapping and not is_aggregatable_field(wazuh_field, mapping):
                raise _s.ValidationError(
                    f"'{value}' maps to a non-aggregatable text field and cannot be used as a correlation key."
                )
        return value

    def validate(self, data):
        """Enforce the Diversity Constraint invariants (ADR-0009) across legs + key.

        A diversity constraint needs the rule's correlation_key to group by, so this is an
        object-level (cross-field) check. On PATCH, fall back to the saved correlation_key.
        """
        from correlations.models import CORRELATION_KEY_NONE
        from correlations.services.search_compiler import validate_diversity_constraint

        # Time-of-day window validation (#440). Runs before the legs early-return so it is
        # enforced on PATCHes that touch only the window. On PATCH, fall back to saved values.
        def _eff(field):
            if field in data:
                return data[field]
            return getattr(self.instance, field, None) if self.instance else None

        start = _eff("time_window_start")
        end = _eff("time_window_end")
        days = list(_eff("time_window_days") or [])
        if bool(start) != bool(end):
            raise _s.ValidationError(
                {"time_window_start": "Provide both a start and end time, or neither."}
            )
        if start and end:
            if start == end:
                raise _s.ValidationError({"time_window_end": "Start and end times must differ."})
            if not days:
                raise _s.ValidationError(
                    {"time_window_days": "Select at least one day for the time window."}
                )
        if days and not (start and end):
            raise _s.ValidationError(
                {"time_window_days": "A time window requires both a start and end time."}
            )
        if len(set(days)) != len(days):
            raise _s.ValidationError({"time_window_days": "Duplicate days are not allowed."})

        legs = data.get("legs")
        if legs is None:
            return data

        corr_key = data.get("correlation_key")
        if corr_key is None:
            corr_key = self.instance.correlation_key if self.instance else CORRELATION_KEY_NONE

        # Absence Firing (#519, ADR-0020): an `lte` leg is only supported for
        # correlation_key = none — a terms aggregation cannot enumerate which keys went
        # silent, so there is no key universe for per-key absence.
        if corr_key != CORRELATION_KEY_NONE:
            for i, leg in enumerate(legs):
                if leg.get("count_operator") == SEARCH_COUNT_OP_LTE:
                    raise _s.ValidationError(
                        {"legs": (
                            f"Leg {i + 1}: the 'at most' (≤) count operator is only "
                            "supported when the correlation key is 'none'."
                        )}
                    )

        mapping = None
        for i, leg in enumerate(legs):
            distinct_field = (leg.get("distinct_field") or "").strip()
            if not distinct_field:
                continue
            if mapping is None:
                mapping = _get_mapping_safe()
            ok, reason = validate_diversity_constraint(
                distinct_field, leg.get("min_distinct", 1), corr_key, mapping
            )
            if not ok:
                raise _s.ValidationError({"legs": f"Leg {i + 1}: {reason}"})
        return data

    def _create_legs(self, rule, legs_data):
        for leg_data in legs_data:
            conditions_data = leg_data.pop("conditions", [])
            leg = SearchRuleLeg.objects.create(rule=rule, **leg_data)
            for cond_data in conditions_data:
                SearchLegCondition.objects.create(leg=leg, **cond_data)

    def create(self, validated_data):
        from correlations.services.search_schedule import sync_rule_schedule
        legs_data = validated_data.pop("legs", [])
        rule = SearchRule.objects.create(**validated_data)
        self._create_legs(rule, legs_data)
        sync_rule_schedule(rule)
        return rule

    def update(self, instance, validated_data):
        from correlations.services.search_schedule import sync_rule_schedule
        legs_data = validated_data.pop("legs", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if legs_data is not None:
            instance.legs.all().delete()
            self._create_legs(instance, legs_data)
        sync_rule_schedule(instance)
        return instance


def _fetch_search_rule(pk):
    try:
        return SearchRule.objects.prefetch_related("legs__conditions", "tests").get(pk=pk)
    except SearchRule.DoesNotExist:
        return None


class SearchRuleListView(APIView):
    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        rules = (
            SearchRule.objects.prefetch_related("legs__conditions", "tests")
            .annotate(firing_count=Count("firings"), last_fired_at=Max("firings__fired_at"))
            .order_by("name")
        )
        return Response(_SearchRuleSerializer(rules, many=True).data)

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err
        serializer = _SearchRuleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        rule = serializer.save()
        return Response(
            _SearchRuleSerializer(
                SearchRule.objects.prefetch_related("legs__conditions", "tests").get(pk=rule.pk)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class SearchRuleDetailView(APIView):
    def get(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_SearchRuleSerializer(rule).data)

    def patch(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = _SearchRuleSerializer(rule, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(
            _SearchRuleSerializer(
                SearchRule.objects.prefetch_related("legs__conditions", "tests").get(pk=pk)
            ).data
        )

    def delete(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        from correlations.services.search_schedule import delete_rule_schedule
        delete_rule_schedule(rule)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SearchRuleRunNowView(APIView):
    """Staff-only: immediately enqueue a SearchRule run."""

    def post(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        result = run_scheduled_search_rule.delay(rule.id)
        return Response({"task_id": result.id}, status=status.HTTP_202_ACCEPTED)


class SearchRuleDebugView(APIView):
    """Staff-only: dry-run a SearchRule and return the raw queries + OpenSearch responses.

    POST body: { "org_slug": "<slug>" }

    No alerts, incidents, or findings are created. Useful for troubleshooting rule
    conditions before enabling a rule in production.
    """

    def post(self, request, pk):
        err = _require_staff(request)
        if err:
            return err

        rule = _fetch_search_rule(pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        org_slug = request.data.get("org_slug")
        if not org_slug:
            return Response({"detail": "org_slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        from correlations.services.search_evaluator import debug_run
        result = debug_run(rule, org)
        return Response(result)


class _InMemoryRelatedManager:
    """Mimics a reverse related manager over a fixed in-memory list.

    Used to build an *unsaved* rule spec that `debug_run`/the compiler can read
    (`rule.legs.prefetch_related(...)`, `leg.conditions.all()`) without any DB rows.
    """

    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def prefetch_related(self, *args, **kwargs):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class _InMemorySpec:
    def __init__(self, fields):
        self.__dict__.update(fields)


def _build_inmemory_search_rule(validated):
    """Build an unsaved, duck-typed SearchRule (with .legs/.conditions) from validated spec data.

    Creates no SearchRule / SearchRuleLeg / SearchLegCondition rows — the result is only
    ever handed to `debug_run`, which reads attributes and queries OpenSearch.
    """
    from correlations.models import CORRELATION_KEY_NONE, _MAX_FINDINGS_DEFAULT

    legs_data = validated.pop("legs", []) or []
    legs = []
    for idx, leg_data in enumerate(legs_data):
        conds = [
            _InMemorySpec({
                "id": None,
                "field_name": c.get("field_name", ""),
                "operator": c.get("operator", ""),
                "value": c.get("value", ""),
            })
            for c in (leg_data.get("conditions") or [])
        ]
        distinct_field = leg_data.get("distinct_field") or ""
        leg = _InMemorySpec({
            "id": None,
            "count": leg_data.get("count", 1),
            "display_order": leg_data.get("display_order", idx),
            "distinct_field": distinct_field,
            "min_distinct": leg_data.get("min_distinct", 1),
            "has_diversity": bool(distinct_field.strip()),
        })
        leg.conditions = _InMemoryRelatedManager(conds)
        legs.append(leg)

    # debug_run takes the target org explicitly; drop any FK from the spec.
    validated.pop("organization", None)
    rule = _InMemorySpec(validated)
    rule.id = None
    rule.legs = _InMemoryRelatedManager(legs)
    rule.include_agentless = bool(getattr(rule, "include_agentless", False))
    rule.window_minutes = getattr(rule, "window_minutes", 60)
    rule.max_findings_per_run = getattr(rule, "max_findings_per_run", _MAX_FINDINGS_DEFAULT)
    rule.correlation_key = getattr(rule, "correlation_key", CORRELATION_KEY_NONE)
    # Time-of-day window (#440): ensure the attributes exist so the compiler can read them.
    rule.time_window_start = getattr(rule, "time_window_start", None)
    rule.time_window_end = getattr(rule, "time_window_end", None)
    rule.time_window_days = getattr(rule, "time_window_days", None) or []
    rule.time_window_mode = getattr(rule, "time_window_mode", "inside") or "inside"
    rule.has_time_window = bool(
        rule.time_window_start and rule.time_window_end and rule.time_window_days
    )
    return rule


class SearchRuleSpecDebugView(APIView):
    """Staff-only: dry-run an UNSAVED rule spec against an org (#437).

    POST body: a full rule spec (the same shape the create/edit form submits to the
    rule list/detail endpoints) plus "org_slug". Builds an in-memory, unsaved rule
    from the spec and runs the same `debug_run` as the saved-rule debug endpoint.
    Persists nothing: no SearchRule, SearchRuleLeg, SearchFinding, Alert or Incident.
    """

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err

        org_slug = request.data.get("org_slug")
        if not org_slug:
            return Response({"detail": "org_slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        spec = {k: v for k, v in request.data.items() if k != "org_slug"}
        serializer = _SearchRuleSerializer(data=spec)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        rule = _build_inmemory_search_rule(dict(serializer.validated_data))

        from correlations.services.search_evaluator import debug_run
        result = debug_run(rule, org)
        return Response(result)


# ── Rule Tests (PRD #439, ADR-0010) ──────────────────────────────────────────

class _SearchRuleTestSerializer(_s.ModelSerializer):
    class Meta:
        model = SearchRuleTest
        fields = [
            "id", "rule", "name", "description", "expect_fire", "samples",
            "last_run_at", "last_status", "last_diagnostics", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "rule", "last_run_at", "last_status", "last_diagnostics",
            "created_at", "updated_at",
        ]

    def validate_samples(self, value):
        if not isinstance(value, list):
            raise _s.ValidationError("samples must be a list of documents.")
        if not all(isinstance(d, dict) for d in value):
            raise _s.ValidationError("each sample document must be a JSON object.")
        from correlations.services.search_test_runner import MAX_SAMPLES_PER_TEST
        if len(value) > MAX_SAMPLES_PER_TEST:
            raise _s.ValidationError(f"at most {MAX_SAMPLES_PER_TEST} sample documents are allowed.")
        return value


class SearchRuleTestListView(APIView):
    """Staff-only: list/create Rule Tests for a saved Scheduled Search Rule."""

    def get(self, request, rule_pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(rule_pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        tests = rule.tests.all()
        return Response(_SearchRuleTestSerializer(tests, many=True).data)

    def post(self, request, rule_pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(rule_pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = _SearchRuleTestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        test = serializer.save(rule=rule)
        return Response(_SearchRuleTestSerializer(test).data, status=status.HTTP_201_CREATED)


def _fetch_test(rule_pk, pk):
    try:
        return SearchRuleTest.objects.select_related("rule").get(pk=pk, rule_id=rule_pk)
    except SearchRuleTest.DoesNotExist:
        return None


class SearchRuleTestDetailView(APIView):
    """Staff-only: retrieve/update/delete a single Rule Test."""

    def get(self, request, rule_pk, pk):
        err = _require_staff(request)
        if err:
            return err
        test = _fetch_test(rule_pk, pk)
        if test is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_SearchRuleTestSerializer(test).data)

    def patch(self, request, rule_pk, pk):
        err = _require_staff(request)
        if err:
            return err
        test = _fetch_test(rule_pk, pk)
        if test is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = _SearchRuleTestSerializer(test, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(_SearchRuleTestSerializer(test).data)

    def delete(self, request, rule_pk, pk):
        err = _require_staff(request)
        if err:
            return err
        test = _fetch_test(rule_pk, pk)
        if test is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        test.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SearchRuleTestRunView(APIView):
    """Staff-only: run a single Rule Test synchronously and return the Test Result."""

    def post(self, request, rule_pk, pk):
        err = _require_staff(request)
        if err:
            return err
        test = _fetch_test(rule_pk, pk)
        if test is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        from correlations.services.search_test_runner import run_rule_test_and_save
        result = run_rule_test_and_save(test)
        return Response(result)


class SearchRuleTestRunAllView(APIView):
    """Staff-only: run all of a rule's Rule Tests and return the aggregate health."""

    def post(self, request, rule_pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(rule_pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from correlations.services.search_test_runner import run_rule_test_and_save

        results = []
        for test in rule.tests.all():
            res = run_rule_test_and_save(test)
            results.append({"id": test.id, "name": test.name, "status": res["status"]})

        summary = _compute_test_summary(rule.tests.all())
        return Response({"summary": summary, "results": results})


class SearchRuleTestGenerateView(APIView):
    """Staff-only: LLM-generate candidate Sample Documents for a rule (review before save)."""

    def post(self, request, rule_pk):
        err = _require_staff(request)
        if err:
            return err
        rule = _fetch_search_rule(rule_pk)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        expect_fire = bool(request.data.get("expect_fire", True))
        scope = request.data.get("scope")

        from correlations.llm.sample_generator import generate_samples

        try:
            result = generate_samples(rule, expect_fire, scope=scope)
        except DraftConfigError as exc:
            logger.warning("SearchRuleTestGenerateView: sample generator config error for rule %s: %s", rule.id, exc)
            return Response(
                {
                    "detail": "Sample generator is unavailable.",
                    "reason": "The sample generator is not configured. Check the server logs for details.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except DraftError as exc:
            logger.warning("SearchRuleTestGenerateView: sample generation failed for rule %s: %s", rule.id, exc)
            return Response(
                {
                    "detail": "Sample generation failed.",
                    "reason": "The model returned an invalid response. Check the server logs for details.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result)


class SearchCatalogView(APIView):
    """Staff-only: return the field catalog for the search rule builder.

    Returns the curated core fields plus all fields populated in the index mapping,
    each annotated with valid operators for that field type. Also returns the rule
    catalog (top rule.id values seen in recent data) for scope-aware grounding.
    """

    def get(self, request):
        err = _require_staff(request)
        if err:
            return err

        from correlations.services.search_compiler import _operators_for_type
        from security.opensearch import OpenSearchClient, OpenSearchError

        scope = request.query_params.get("scope", "all")

        # Resolve agent IDs for scope-aware rule catalog.
        agent_ids: list | None = None
        if scope != "all":
            try:
                org = Organization.objects.get(slug=scope)
                from security.wazuh import WazuhClient, WazuhAPIError, WazuhAuthError
                try:
                    raw_agents = WazuhClient().get_agents(org.wazuh_group)
                    agent_ids = [a["id"] for a in raw_agents]
                except (WazuhAPIError, WazuhAuthError):
                    agent_ids = []
            except Organization.DoesNotExist:
                return Response({"detail": "Unknown scope."}, status=status.HTTP_400_BAD_REQUEST)

        client = OpenSearchClient()

        # Fetch live mapping.
        mapping: dict = {}
        try:
            mapping = client.get_field_mapping()
        except OpenSearchError:
            logger.warning("SearchCatalogView: could not fetch field mapping")

        # Fetch rule catalog.
        rule_catalog: dict = {}
        try:
            rule_catalog = client.get_rule_catalog(agent_ids=agent_ids)
        except OpenSearchError:
            logger.warning("SearchCatalogView: could not fetch rule catalog")

        core_field_names = {f["value"] for f in _SEARCH_CORE_FIELDS}

        # Annotate core fields with operators from live mapping (fall back to declared type).
        core_fields = []
        for f in _SEARCH_CORE_FIELDS:
            live_type = mapping.get(f["value"], f["type"])
            core_fields.append({
                **f,
                "type": live_type,
                "operators": _operators_for_type(live_type),
                "core": True,
            })

        # Non-core mapping fields for autocomplete.
        extra_fields = [
            {
                "value": field,
                "label": field,
                "type": ftype,
                "operators": _operators_for_type(ftype),
                "core": False,
            }
            for field, ftype in sorted(mapping.items())
            if field not in core_field_names
        ]

        return Response({
            "core_fields": core_fields,
            "fields": extra_fields,
            "rule_catalog": rule_catalog,
        })


# ── Per-org system search rule mute views ─────────────────────────────────────

class OrgSystemSearchRulesView(APIView):
    """List system search rules with per-org mute status. Staff only."""

    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        org, err = _get_org_for_staff(request)
        if err:
            return err

        system_rules = (
            SearchRule.objects
            .filter(organization=None)
            .prefetch_related("legs__conditions")
            .order_by("name")
        )
        muted_ids = set(
            SearchRuleMute.objects.filter(organization=org).values_list("rule_id", flat=True)
        )
        data = []
        for rule in system_rules:
            row = _SearchRuleSerializer(rule).data
            row["muted"] = rule.id in muted_ids
            data.append(row)
        return Response(data)


class OrgSystemSearchRuleMuteView(APIView):
    """Create or remove a mute record for a system search rule + org pair. Staff only."""

    def _resolve(self, request, pk):
        err = _require_staff(request)
        if err:
            return None, None, err
        org, err = _get_org_for_staff(request)
        if err:
            return None, None, err
        try:
            rule = SearchRule.objects.get(pk=pk, organization=None)
        except SearchRule.DoesNotExist:
            return None, None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return rule, org, None

    def post(self, request, pk):
        rule, org, err = self._resolve(request, pk)
        if err:
            return err
        SearchRuleMute.objects.get_or_create(organization=org, rule=rule)
        return Response({"rule_id": rule.id, "muted": True})

    def delete(self, request, pk):
        rule, org, err = self._resolve(request, pk)
        if err:
            return err
        SearchRuleMute.objects.filter(organization=org, rule=rule).delete()
        return Response({"rule_id": rule.id, "muted": False})
