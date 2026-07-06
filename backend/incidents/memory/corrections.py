"""Classification Correction capture + the Classify-accuracy metric (ADR-0030, slice #665).

When a human overturns the Triage Classify phase's output — changes the Subject, overrides
severity, or reverses the disposition — that labelled correction is the strongest learning
signal in the system. Recording it powers the Classify-accuracy metric, enriches Precedents
(via ``precedents.was_corrected``), feeds the distillation sweep, and contradicts the
Lesson that drove the wrong call.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

ACCURACY_WINDOW_DAYS = 30


def agent_classification(incident) -> dict | None:
    """The agent's original Classify call, read from the Classify AI-triage comment.

    Returns ``{"subject_slug", "severity"}`` or ``None`` if the incident was never triaged.
    The Classify comment is the earliest ``ai_triage`` comment carrying a
    ``subject_recommendation`` in its metadata (the Work comment does not).
    """
    from incidents.models import Comment

    for c in (Comment.objects.filter(incident=incident, kind=Comment.KIND_AI_TRIAGE)
              .order_by("created_at")):
        meta = c.metadata or {}
        if "subject_recommendation" in meta or "severity_recommendation" in meta:
            return {
                "subject_slug": meta.get("subject_recommendation"),
                "severity": meta.get("severity_recommendation"),
            }
    return None


def _applied_lesson_ids(incident):
    from incidents.models import Comment

    ids = set()
    for c in Comment.objects.filter(incident=incident, kind=Comment.KIND_AI_TRIAGE):
        for lid in (c.metadata or {}).get("applied_lesson_ids", []) or []:
            ids.add(lid)
    return ids


def _contradict_driving_lessons(incident):
    """Bump contradiction_count on every Lesson this incident's triage applied."""
    from incidents.memory.lessons import apply_contradiction
    from incidents.models import TriageLesson

    ids = _applied_lesson_ids(incident)
    for lesson in TriageLesson.objects.filter(id__in=ids):
        apply_contradiction(lesson)


def capture_classification_correction(incident, *, actor, new_subject=None, new_severity=None):
    """Record a Classification Correction when a human overturns the agent's Classify call.

    Compares the human's new Subject/severity to the agent's original recommendation; records
    a correction only when they actually differ. Returns the created ClassificationCorrection
    or ``None`` when there is nothing to record (no triage, or the human agreed).
    """
    from incidents.models import ClassificationCorrection, Subject

    baseline = agent_classification(incident)
    if baseline is None:
        return None

    agent_subject = None
    if baseline.get("subject_slug"):
        agent_subject = Subject.objects.filter(slug=baseline["subject_slug"]).first()
    agent_severity = baseline.get("severity") or ""

    subject_changed = (
        new_subject is not None
        and (agent_subject is None or new_subject.id != agent_subject.id)
    )
    severity_changed = (
        new_severity is not None and agent_severity and new_severity != agent_severity
    )
    if not (subject_changed or severity_changed):
        return None

    correction = ClassificationCorrection.objects.create(
        incident=incident,
        agent_subject=agent_subject,
        human_subject=new_subject if subject_changed else None,
        agent_severity=agent_severity if severity_changed else "",
        human_severity=new_severity if severity_changed else "",
        actor=actor,
    )
    _contradict_driving_lessons(incident)
    return correction


def classify_accuracy(since=None) -> dict:
    """Classify-accuracy over a window: agreement between the agent's original Subject and
    the incident's current (human-ratified) Subject.

    Returns ``{"total", "agreements", "accuracy"}``. ``total`` counts incidents that were
    triaged (have an agent Subject call) and now carry a Subject. ``accuracy`` is the
    agreement ratio, or ``None`` when there is no data yet.
    """
    from incidents.models import Comment, Incident

    since = since or (timezone.now() - timedelta(days=ACCURACY_WINDOW_DAYS))
    triaged = (
        Incident.objects.filter(
            subject__isnull=False, updated_at__gte=since,
            comments__kind=Comment.KIND_AI_TRIAGE,
        )
        .select_related("subject")
        .distinct()
    )
    total = 0
    agreements = 0
    for inc in triaged:
        baseline = agent_classification(inc)
        if baseline is None or not baseline.get("subject_slug"):
            continue
        total += 1
        if baseline["subject_slug"] == inc.subject.slug:
            agreements += 1
    accuracy = (agreements / total) if total else None
    return {"total": total, "agreements": agreements, "accuracy": accuracy}


# ── Prometheus gauge (best-effort; the aggregation above is the tested contract) ──────

try:
    from prometheus_client import Gauge

    _ACCURACY_GAUGE = Gauge(
        "vels_triage_classify_accuracy",
        "Agreement between the Triage Classify subject and the human-ratified subject.",
    )
except Exception:  # pragma: no cover - prometheus_client always present, but never fatal
    _ACCURACY_GAUGE = None


def update_classify_accuracy_gauge():
    """Recompute the metric and publish it to the Prometheus gauge. Best-effort."""
    stats = classify_accuracy()
    if _ACCURACY_GAUGE is not None and stats["accuracy"] is not None:
        try:
            _ACCURACY_GAUGE.set(stats["accuracy"])
        except Exception as exc:  # pragma: no cover
            logger.warning("update_classify_accuracy_gauge: set failed: %s", exc)
    return stats
