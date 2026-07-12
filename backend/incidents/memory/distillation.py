"""The batched distillation sweep — the single learning engine (ADR-0030, slices #663/#664).

A human close/correction only *tags* an Incident as eligible evidence; this sweep clusters
recent eligible Incidents by Subject + source_kind, requires >= N corroborating cases, checks
there is no covering active/proposed Lesson, and emits `proposed` Org Lessons (#663). Global
promotion across >= K orgs is layered on in #664.

Eligible signal is strictly HUMAN-ratified: incidents a human closed, plus Classification
Corrections (#665). Classify's false-positive auto-close, stale auto-close, and
duplicate/supersede closes are excluded — the agent never trains on its own or a machine's
disposition.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MIN_EVIDENCE = 3          # N: corroborating human-closed incidents before proposing
MIN_ORGS_FOR_GLOBAL = 2   # K: distinct orgs before a Global Lesson is proposed (#664)
LOOKBACK_DAYS = 90
_COMMENT_SNIPPET = 200
RUN_RETENTION = 200       # keep this many DistillationRun records (#697); prune older


def _lookback_since():
    days = int(getattr(settings, "TRIAGE_DISTILLATION_LOOKBACK_DAYS", LOOKBACK_DAYS))
    return timezone.now() - timedelta(days=days)


def was_human_closed(incident) -> bool:
    """True iff a HUMAN closed this incident (the only disposition we learn from).

    A human close records an `incident_updated` IncidentEvent with a non-null actor whose
    change set moves state to `closed`. Classify FP auto-close, the stale auto-closer, and
    supersede all pass actor=None, so they are excluded.
    """
    from incidents.models import IncidentEvent

    for ev in IncidentEvent.objects.filter(
        incident=incident, kind="incident_updated", actor__isnull=False
    ):
        changes = (ev.payload or {}).get("changes") or {}
        state_change = changes.get("state") or {}
        if state_change.get("new") == "closed":
            return True
    return False


def eligible_incidents(since=None):
    """Resolved incidents that are valid learning evidence, most-recent first.

    Human-closed, carry a Subject (the cluster key), are not duplicate closures, and fall
    within the lookback window.
    """
    from incidents.models import Incident

    since = since or _lookback_since()
    candidates = (
        Incident.objects
        .filter(state=Incident.STATE_CLOSED, subject__isnull=False,
                closure_reason__isnull=False, updated_at__gte=since)
        .exclude(closure_reason=Incident.CLOSURE_DUPLICATE)
        .select_related("organization", "subject")
        .order_by("-updated_at")
    )
    return [inc for inc in candidates if was_human_closed(inc)]


def _cluster_payload(subject, source_kind, incidents):
    from incidents.models import Comment

    rows = []
    for inc in incidents:
        comments = list(
            Comment.objects.filter(incident=inc).exclude(body="")
            .order_by("-created_at").values_list("body", flat=True)[:2]
        )
        rows.append({
            "title": inc.title,
            "description": (inc.description or "")[:400],
            "closure_reason": inc.closure_reason,
            "severity": inc.severity,
            "resolution_comments": [" ".join(c.split())[:_COMMENT_SNIPPET] for c in comments],
        })
    return {"subject": subject.name, "source_kind": source_kind, "incidents": rows}


def _has_covering_lesson(organization_id, subject_id, source_kind):
    """A Lesson already covers this cluster if an active/proposed one matches its key."""
    from incidents.models import TriageLesson

    return TriageLesson.objects.filter(
        organization_id=organization_id, subject_id=subject_id, source_kind=source_kind,
        status__in=[TriageLesson.STATUS_ACTIVE, TriageLesson.STATUS_PROPOSED],
    ).exists()


def _record_outcome(outcomes, *, tier, subject, source_kind, organization, incidents, outcome):
    """Append one cluster decision to an observability collector, if one is supplied (#697).

    Records only the cluster key and the decision reason — never raw incident bodies — so
    the run summary stays a lightweight, staff-only audit of what the sweep considered.
    """
    if outcomes is None:
        return
    outcomes.append({
        "tier": tier,
        "organization": organization.slug if organization is not None else None,
        "subject": subject.name if subject is not None else None,
        "source_kind": source_kind,
        "evidence_count": len(incidents),
        "outcome": outcome,
    })


def run_distillation_sweep(*, provider=None, since=None, min_evidence=MIN_EVIDENCE,
                           min_orgs=MIN_ORGS_FOR_GLOBAL, outcomes=None):
    """Cluster eligible evidence and propose Org Lessons. Returns the proposed Lessons.

    Idempotent across runs via the covering-lesson guard: a cluster already carrying an
    active/proposed Lesson is skipped, so re-running never floods the queue.

    When ``outcomes`` is a list, each cluster's decision (proposed / why-skipped) is
    appended to it for observability (#697). This never affects what gets proposed.
    """
    from incidents.llm.factory import get_triage_provider
    from incidents.memory.lessons import propose_lesson
    from incidents.models import DistillationRun, TriageLesson

    if provider is None:
        provider = get_triage_provider()

    # Cluster by (org, subject, source_kind) — Org-tier proposals live within one tenant.
    clusters = defaultdict(list)
    for inc in eligible_incidents(since=since):
        clusters[(inc.organization_id, inc.subject_id, inc.source_kind)].append(inc)

    proposed = []
    for (org_id, subject_id, source_kind), incidents in clusters.items():
        subject = incidents[0].subject
        record = lambda outcome: _record_outcome(  # noqa: E731 — local closure over the key
            outcomes, tier="org", subject=subject, source_kind=source_kind,
            organization=incidents[0].organization, incidents=incidents, outcome=outcome)
        if len(incidents) < min_evidence:
            record(DistillationRun.OUTCOME_INSUFFICIENT_EVIDENCE)
            continue
        if _has_covering_lesson(org_id, subject_id, source_kind):
            record(DistillationRun.OUTCOME_COVERING_LESSON)
            continue
        try:
            draft = provider.distill_triage_lesson(
                _cluster_payload(subject, source_kind, incidents)
            ) or {}
        except Exception as exc:
            logger.warning("distillation: distiller failed for subject %s: %s", subject_id, exc)
            record(DistillationRun.OUTCOME_DISTILLER_ERROR)
            continue
        guidance = (draft.get("guidance") or "").strip()
        if not guidance:
            record(DistillationRun.OUTCOME_EMPTY_GUIDANCE)
            continue
        lesson = propose_lesson(
            incidents[0], guidance=guidance, selector=(draft.get("selector") or "").strip(),
            source_kind=source_kind, provenance=TriageLesson.PROV_DISTILLED,
            organization=incidents[0].organization, evidence=incidents,
        )
        proposed.append(lesson)
        record(DistillationRun.OUTCOME_PROPOSED)

    proposed.extend(_propose_global_lessons(provider, since=since, min_orgs=min_orgs,
                                            min_evidence=min_evidence, outcomes=outcomes))
    return proposed


def _propose_global_lessons(provider, *, since=None, min_orgs=MIN_ORGS_FOR_GLOBAL,
                            min_evidence=MIN_EVIDENCE, outcomes=None):
    """Promote a cross-org recurring pattern to a scrubbed, generalised Global Lesson (#664).

    Cluster eligible incidents by (subject, source_kind) ACROSS orgs; when the pattern spans
    >= K distinct orgs (and enough total cases), ask the distiller for a GENERALISED lesson
    carrying no tenant specifics (ADR-0031) and propose it as a Global Lesson (org=None).
    The human scrub at approval — not this step — is the isolation guarantee; evidence links
    stay staff-only.
    """
    from incidents.memory.lessons import propose_lesson
    from incidents.models import DistillationRun, TriageLesson

    clusters = defaultdict(list)
    for inc in eligible_incidents(since=since):
        clusters[(inc.subject_id, inc.source_kind)].append(inc)

    proposed = []
    for (subject_id, source_kind), incidents in clusters.items():
        org_ids = {inc.organization_id for inc in incidents}
        # Only clusters that already span enough orgs are Global candidates; the rest are
        # purely Org-tier concerns and are recorded there, not here (avoids double-counting).
        if len(org_ids) < min_orgs:
            continue
        subject = incidents[0].subject
        record = lambda outcome: _record_outcome(  # noqa: E731 — local closure over the key
            outcomes, tier="global", subject=subject, source_kind=source_kind,
            organization=None, incidents=incidents, outcome=outcome)
        if len(incidents) < min_evidence:
            record(DistillationRun.OUTCOME_INSUFFICIENT_EVIDENCE)
            continue
        if _has_covering_lesson(None, subject_id, source_kind):
            record(DistillationRun.OUTCOME_COVERING_LESSON)
            continue
        payload = _cluster_payload(subject, source_kind, incidents)
        # Signal the distiller to generalise/scrub for a fleet-wide lesson.
        payload["scope"] = "global"
        payload["org_count"] = len(org_ids)
        try:
            draft = provider.distill_triage_lesson(payload) or {}
        except Exception as exc:
            logger.warning("distillation: global distiller failed for subject %s: %s",
                           subject_id, exc)
            record(DistillationRun.OUTCOME_DISTILLER_ERROR)
            continue
        guidance = (draft.get("guidance") or "").strip()
        if not guidance:
            record(DistillationRun.OUTCOME_EMPTY_GUIDANCE)
            continue
        lesson = propose_lesson(
            incidents[0], guidance=guidance, selector=(draft.get("selector") or "").strip(),
            source_kind=source_kind, provenance=TriageLesson.PROV_DISTILLED,
            organization=None, evidence=incidents,  # explicit Global (org=None)
        )
        proposed.append(lesson)
        record(DistillationRun.OUTCOME_PROPOSED)
    return proposed


def run_and_record_sweep(*, provider=None, since=None):
    """Run one sweep and persist an inspectable DistillationRun summary (#697).

    Thin observability wrapper over ``run_distillation_sweep`` used by the scheduled task:
    it collects per-cluster decisions, records eligible/cluster/proposed counts, and prunes
    old run rows. Returns the created DistillationRun. The learning outcome is unchanged —
    the same Lessons are proposed whether or not this wrapper is used.
    """
    from incidents.models import DistillationRun

    outcomes = []
    started = timezone.now()
    proposed = run_distillation_sweep(provider=provider, since=since, outcomes=outcomes)
    run = DistillationRun.objects.create(
        started_at=started,
        finished_at=timezone.now(),
        eligible_count=len(eligible_incidents(since=since)),
        cluster_count=len(outcomes),
        proposed_count=len(proposed),
        proposed_global_count=sum(1 for lesson in proposed if lesson.is_global),
        clusters=outcomes,
    )
    _prune_runs()
    return run


def _prune_runs():
    """Keep only the most recent ``RUN_RETENTION`` DistillationRun rows."""
    from incidents.models import DistillationRun

    keep_ids = list(
        DistillationRun.objects.order_by("-started_at").values_list("id", flat=True)[:RUN_RETENTION]
    )
    DistillationRun.objects.exclude(id__in=keep_ids).delete()
