"""Staff-only Triage Lesson review — the proposed → active gate (ADR-0030, slice #662).

Nothing the machine learns takes effect unreviewed: a distilled or agent-proposed Lesson
is inert (``proposed``) until a SOC staff member approves it here. Approval carries an
**edit** — for a Global Lesson that edit is the human scrub that makes cross-tenant
learning safe (ADR-0031), so it is the human approval, not any automated scrubber, that is
the isolation guarantee.
"""
from django.utils import timezone

_EDITABLE_FIELDS = ("guidance", "selector", "source_kind")


class LessonReviewError(Exception):
    """Raised on an invalid review transition (e.g. approving an archived Lesson).

    ``code`` is a stable, safe identifier the API layer maps to a caller-facing
    message, so the exception text (kept for logs) is never echoed to clients.
    """

    def __init__(self, message, *, code="invalid_transition"):
        super().__init__(message)
        self.code = code


def _apply_edits(lesson, edits):
    if not edits:
        return
    for field in _EDITABLE_FIELDS:
        if field in edits and edits[field] is not None:
            setattr(lesson, field, edits[field])


def approve_lesson(lesson, *, staff, edits=None):
    """Approve a proposed (or suspended) Lesson, applying edits, and activate it.

    Edit-on-approve is always available so a staff member can scrub/tighten the guidance
    before it goes live — mandatory for a Global Lesson going fleet-wide.
    """
    from incidents.models import TriageLesson

    if lesson.status not in (TriageLesson.STATUS_PROPOSED, TriageLesson.STATUS_SUSPENDED):
        raise LessonReviewError(
            f"cannot approve a lesson in status '{lesson.status}'", code="not_approvable"
        )
    _apply_edits(lesson, edits)
    lesson.status = TriageLesson.STATUS_ACTIVE
    lesson.approved_by = staff
    lesson.contradiction_count = 0  # a fresh approval clears prior contradictions
    lesson.save(update_fields=[*_EDITABLE_FIELDS, "status", "approved_by",
                               "contradiction_count", "updated_at"])
    return lesson


def reject_lesson(lesson, *, staff):
    """Reject a proposed Lesson — archived, never selected, kept for audit."""
    from incidents.models import TriageLesson

    if lesson.status == TriageLesson.STATUS_ACTIVE:
        raise LessonReviewError(
            "cannot reject an active lesson; suspend it instead", code="reject_active"
        )
    lesson.status = TriageLesson.STATUS_ARCHIVED
    lesson.save(update_fields=["status", "updated_at"])
    return lesson


def suspend_lesson(lesson, *, staff):
    """Suspend an active Lesson — instant, retroactive-safe kill switch."""
    from incidents.models import TriageLesson

    lesson.status = TriageLesson.STATUS_SUSPENDED
    lesson.save(update_fields=["status", "updated_at"])
    return lesson


def author_lesson(*, subject, guidance, staff, organization=None, source_kind="",
                  selector=""):
    """A staff member writes a Lesson directly — active immediately (staff_authored).

    organization=None ⇒ a Global Lesson; set ⇒ an Org Lesson.
    """
    from incidents.models import TriageLesson

    return TriageLesson.objects.create(
        organization=organization, subject=subject, source_kind=source_kind or "",
        selector=selector or "", guidance=guidance,
        status=TriageLesson.STATUS_ACTIVE, provenance=TriageLesson.PROV_STAFF,
        created_by=staff, approved_by=staff, last_applied_at=None,
    )
