"""Staff-only Triage Lesson review queue API (ADR-0030/0031, slice #662).

Tenants are entirely outside this surface — every endpoint is staff-guarded, consistent
with Triage/Hunt/Attack-Map. A Global Lesson's evidence links are staff-only here and are
never surfaced to a tenant anywhere.
"""
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.memory import review
from incidents.models import ClassificationCorrection, DistillationRun, Subject, TriageLesson
from incidents.views import _require_staff
from security.models import Organization


class TriageLessonSerializer(serializers.ModelSerializer):
    tier = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    # Staff-only: the resolved incidents that justify the lesson (audit + grounding).
    evidence_display_ids = serializers.SerializerMethodField()

    class Meta:
        model = TriageLesson
        fields = [
            "id", "tier", "organization_slug", "subject", "subject_name", "source_kind",
            "selector", "guidance", "status", "provenance", "applied_count",
            "contradiction_count", "evidence_display_ids", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_tier(self, obj):
        return "global" if obj.is_global else "org"

    def get_evidence_display_ids(self, obj):
        return list(obj.evidence.values_list("display_id", flat=True))


class LessonReviewQueueView(APIView):
    """List Triage Lessons for review (proposed by default) and author new ones."""

    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        wanted = request.query_params.get("status", TriageLesson.STATUS_PROPOSED)
        qs = TriageLesson.objects.select_related("subject", "organization").prefetch_related("evidence")
        if wanted != "all":
            qs = qs.filter(status=wanted)
        return Response(TriageLessonSerializer(qs, many=True).data)

    def post(self, request):
        err = _require_staff(request)
        if err:
            return err
        subject_id = request.data.get("subject")
        guidance = (request.data.get("guidance") or "").strip()
        if not subject_id or not guidance:
            return Response({"detail": "subject and guidance are required."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            subject = Subject.objects.get(pk=subject_id)
        except Subject.DoesNotExist:
            return Response({"detail": "No such subject."}, status=status.HTTP_404_NOT_FOUND)
        organization = None
        org_slug = request.data.get("organization")
        if org_slug:
            try:
                organization = Organization.objects.get(slug=org_slug)
            except Organization.DoesNotExist:
                return Response({"detail": "No such organization."}, status=status.HTTP_404_NOT_FOUND)
        lesson = review.author_lesson(
            subject=subject, guidance=guidance, staff=request.user, organization=organization,
            source_kind=(request.data.get("source_kind") or "").strip(),
            selector=(request.data.get("selector") or "").strip(),
        )
        return Response(TriageLessonSerializer(lesson).data, status=status.HTTP_201_CREATED)


class DistillationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = DistillationRun
        fields = [
            "id", "started_at", "finished_at", "eligible_count", "cluster_count",
            "proposed_count", "proposed_global_count", "clusters",
        ]
        read_only_fields = fields


class DistillationRunListView(APIView):
    """Recent distillation-sweep run summaries for the review surface (#697). Staff-only.

    Read-only observability into what the background sweep considered and why it did or did
    not propose Lessons. The per-cluster `clusters` breakdown is staff-only, consistent with
    every other Triage Lesson evidence surface (ADR-0031)."""

    _DEFAULT_LIMIT = 20

    def get(self, request):
        err = _require_staff(request)
        if err:
            return err
        try:
            limit = min(int(request.query_params.get("limit", self._DEFAULT_LIMIT)), 100)
        except (TypeError, ValueError):
            limit = self._DEFAULT_LIMIT
        runs = DistillationRun.objects.all()[:limit]
        return Response(DistillationRunSerializer(runs, many=True).data)


class ClassificationCorrectionSerializer(serializers.ModelSerializer):
    """A human overturning the Classify call, flattened for the subject troubleshooting view.

    Carries cross-org incident references, so — like every other correction/lesson evidence
    surface — it is only ever served staff-only (ADR-0031)."""

    incident_display_id = serializers.CharField(source="incident.display_id", read_only=True)
    incident_title = serializers.CharField(source="incident.title", read_only=True)
    organization_slug = serializers.CharField(source="incident.organization.slug", read_only=True)
    agent_subject_name = serializers.CharField(source="agent_subject.name", read_only=True, default=None)
    human_subject_name = serializers.CharField(source="human_subject.name", read_only=True, default=None)
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = ClassificationCorrection
        fields = [
            "id", "incident_display_id", "incident_title", "organization_slug",
            "agent_subject_name", "human_subject_name",
            "agent_severity", "human_severity",
            "agent_disposition", "human_disposition",
            "actor_username", "created_at",
        ]
        read_only_fields = fields


class SubjectCorrectionsView(APIView):
    """Classification Corrections that touch one Subject — a Classify-accuracy troubleshooting
    surface (ADR-0030). Staff-only.

    Returns every correction where the Subject was either the agent's (wrong) Classify call
    or the human's fix — i.e. cases where the model over-applied the Subject or missed it —
    newest first. Corrections reference incidents across tenants, so this stays staff-only,
    consistent with the Triage Lesson evidence surfaces."""

    _DEFAULT_LIMIT = 50

    def get(self, request, pk):
        err = _require_staff(request)
        if err:
            return err
        try:
            limit = min(int(request.query_params.get("limit", self._DEFAULT_LIMIT)), 200)
        except (TypeError, ValueError):
            limit = self._DEFAULT_LIMIT
        qs = (
            ClassificationCorrection.objects
            .filter(Q(agent_subject_id=pk) | Q(human_subject_id=pk))
            .select_related("incident", "incident__organization", "agent_subject",
                            "human_subject", "actor")
            .order_by("-created_at")[:limit]
        )
        return Response(ClassificationCorrectionSerializer(qs, many=True).data)


class LessonReviewActionView(APIView):
    """Approve (with edits), reject, or suspend a single Triage Lesson."""

    _ACTIONS = {"approve", "reject", "suspend"}

    def post(self, request, pk, action):
        err = _require_staff(request)
        if err:
            return err
        if action not in self._ACTIONS:
            return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lesson = TriageLesson.objects.get(pk=pk)
        except TriageLesson.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            if action == "approve":
                edits = {k: request.data.get(k) for k in ("guidance", "selector", "source_kind")
                         if k in request.data}
                review.approve_lesson(lesson, staff=request.user, edits=edits)
            elif action == "reject":
                review.reject_lesson(lesson, staff=request.user)
            else:
                review.suspend_lesson(lesson, staff=request.user)
        except review.LessonReviewError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TriageLessonSerializer(lesson).data)
