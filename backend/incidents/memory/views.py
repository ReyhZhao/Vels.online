"""Staff-only Triage Lesson review queue API (ADR-0030/0031, slice #662).

Tenants are entirely outside this surface — every endpoint is staff-guarded, consistent
with Triage/Hunt/Attack-Map. A Global Lesson's evidence links are staff-only here and are
never surfaced to a tenant anywhere.
"""
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from incidents.memory import review
from incidents.models import Subject, TriageLesson
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
