"""Triage Lesson selection and authoring (ADR-0030, slices #661/#666).

A **Triage Lesson** is a distilled disposition heuristic keyed on Subject (+ optional
source_kind). ``select_lessons`` is the read path used by the gated Work phase; it hard-
filters on the incident's Subject, source_kind, and tenant scope (own-org Org Lessons +
Global Lessons), and caps the result so a popular Subject cannot bloat the prompt. A
Lesson only *informs* — it never authorizes an action (ADR-0025 gates still hold).
"""
import logging

from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

INJECT_CAP = 5

# Sentinel so a caller can pass organization=None to mean an explicit Global Lesson,
# distinct from "not specified — default to the incident's org".
_UNSET = object()


def select_lessons(incident, *, cap=INJECT_CAP):
    """Return active Triage Lessons that apply to `incident`, most-relevant first, capped.

    Scope (ADR-0031): the incident's OWN organisation's Org Lessons plus all Global
    Lessons — never another tenant's Org Lessons. A Lesson matches when its Subject equals
    the incident's Subject and its source_kind is blank (any) or equals the incident's.
    Returns ``[]`` when the incident has no Subject (the key). Near-duplicate consolidation
    is applied on top of the cap (slice #666).
    """
    from incidents.models import TriageLesson

    if incident.subject_id is None:
        return []

    qs = (
        TriageLesson.objects
        .filter(status=TriageLesson.STATUS_ACTIVE, subject_id=incident.subject_id)
        .filter(Q(organization_id=incident.organization_id) | Q(organization__isnull=True))
        .filter(Q(source_kind="") | Q(source_kind=incident.source_kind))
        # Org Lessons before Global (more specific to this tenant — nulls last); then
        # most-applied, then most-recent.
        .order_by(F("organization_id").asc(nulls_last=True), "-applied_count", "-updated_at")
    )
    lessons = _consolidate(list(qs))
    return lessons[:cap]


def _consolidate(lessons):
    """Drop near-duplicate Lessons so the cap is not spent on redundant guidance (#666).

    Two Lessons are near-duplicates when their guidance normalises to the same token
    signature. The first (higher-ranked) survivor wins; an Org Lesson thus shadows a
    Global one that says the same thing.
    """
    seen = set()
    out = []
    for lesson in lessons:
        sig = _signature(lesson.guidance)
        # An empty signature (very short guidance) carries no dedupe signal — keep it.
        if sig and sig in seen:
            continue
        if sig:
            seen.add(sig)
        out.append(lesson)
    return out


def _signature(text: str) -> frozenset:
    return frozenset(w for w in (text or "").lower().split() if len(w) > 3)


def serialize_lesson(lesson) -> dict:
    """Compact dict form for prompt injection and the retrieval tool."""
    return {
        "id": lesson.id,
        "tier": "global" if lesson.is_global else "org",
        "source_kind": lesson.source_kind or "any",
        "selector": lesson.selector,
        "guidance": lesson.guidance,
    }


def lessons_brief(lessons) -> str:
    """Render selected Lessons into a Work-seed prompt block."""
    if not lessons:
        return ""
    lines = [
        "Triage Lessons — what the SOC has learned about incidents like this. Treat them as "
        "priors that inform your judgement; they do NOT authorize any action on their own:"
    ]
    for l in lessons:
        d = serialize_lesson(l)
        applies = f" (applies when: {d['selector']})" if d["selector"] else ""
        lines.append(f"  - [{d['tier']}/{d['source_kind']}] {d['guidance']}{applies}")
    return "\n".join(lines)


def apply_contradiction(lesson):
    """Register that a human resolved against this Lesson (ADR-0030). Slice #665 bumps the
    counter; slice #666 adds the auto-suspend-at-threshold behaviour."""
    from django.db.models import F
    from incidents.models import TriageLesson

    TriageLesson.objects.filter(pk=lesson.pk).update(
        contradiction_count=F("contradiction_count") + 1
    )
    lesson.refresh_from_db(fields=["contradiction_count"])
    return lesson


def record_applied(lessons):
    """Mark Lessons as applied when they are injected into a Work run (audit + ranking)."""
    from incidents.models import TriageLesson

    ids = [l.id for l in lessons]
    if not ids:
        return
    now = timezone.now()
    (TriageLesson.objects.filter(id__in=ids)
     .update(last_applied_at=now))
    # applied_count bumped separately so F() import stays local.
    from django.db.models import F
    TriageLesson.objects.filter(id__in=ids).update(applied_count=F("applied_count") + 1)


def propose_lesson(incident, *, guidance, selector="", source_kind="",
                   provenance, organization=_UNSET, created_by=None, evidence=None):
    """Create a `proposed` Triage Lesson (inert until a staff member approves it).

    Used by the agent's `propose_lesson` tool (provenance=agent_proposed) and by the
    distillation sweep (provenance=distilled_from_human_close). Org-tier by default
    (the incident's organisation); pass ``organization=None`` for an explicit Global
    proposal (#664), or a specific Organization to override.
    """
    from incidents.models import TriageLesson

    if incident.subject_id is None:
        raise ValueError("cannot propose a lesson for an incident with no subject")
    org = incident.organization if organization is _UNSET else organization
    lesson = TriageLesson.objects.create(
        organization=org,
        subject_id=incident.subject_id,
        source_kind=source_kind or (incident.source_kind or ""),
        selector=selector or "",
        guidance=guidance,
        status=TriageLesson.STATUS_PROPOSED,
        provenance=provenance,
        created_by=created_by,
    )
    if evidence:
        lesson.evidence.set(evidence)
    return lesson
