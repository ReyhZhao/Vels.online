"""Retrospective measurement of whether semantic (embedding) precedent retrieval would
recover **Precedents** that the current entity/keyword retrieval (`precedents.build_precedents`)
misses — the go/no-go evidence for issue #657 (semantic retrieval via vector DB, v2).

This is a *background research* job, not a production surface. It stands up **no** vector
store and touches **no** hot triage path: for each human **Classification Correction** it
reconstructs the precedent corpus that existed at the corrected Incident's Classify time,
then compares what the live keyword ``Q`` would have surfaced against a brute-force cosine
ranking over that same corpus. Per ADR-0030 v1 deliberately has no vector store; the #657
trigger is "build only if keyword retrieval materially misses cases the model should catch".

Ground truth is **correction-anchored** (ADR-0030's strongest self-learning signal): the
"right" precedent for a corrected Incident is a same-org resolved Incident carrying the
*human's final Subject*. Only subject corrections qualify (severity/disposition-only
corrections have no clean "right precedent by subject", so they are skipped, not scored).

Strictly per-org throughout (ADR-0031): the corpus is hard-filtered on the corrected
Incident's own **Organization** — there is no cross-tenant path here either. This job must
never become a backdoor that ranks one tenant's raw case against another's.

Reconstruction is deliberately approximate: the corpus is time-bounded to Incidents
concluded before the corrected Incident was created (the fairness axis that matters), but
the query's entity set is read from *current* state. IOCs/assets are almost always linked
at creation, so drift is small; if the numbers look polluted, that is the signal to build
the exact live-shadow log instead.
"""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .precedents import _match_q, _matching_keys

DEFAULT_TOP_K = 5          # mirrors precedents.PRECEDENT_LIMIT — the injection budget
MIN_SAMPLE = 20            # below this many scored cases the partition has no power
BUILD_THRESHOLD = 0.25     # headline ≥ 25% → trigger fired, build the store (#657)
CLOSE_THRESHOLD = 0.10     # headline < 10% → keyword suffices, close #657 with evidence

# Bucket for each qualifying (subject) correction. The right precedent (a corpus incident
# with the human's final subject) lands in exactly one:
CORPUS_GAP = "corpus_gap"                    # no such prior existed → retrieval can't help
KEYWORD_COVERED = "keyword_covered"          # keyword already surfaced the right prior
EMBEDDING_RECOVERED = "embedding_recovered"  # keyword missed it, embedding surfaced it ⭐
BOTH_MISSED = "both_missed"                  # prior existed, neither surfaced it in top-K

VERDICT_INSUFFICIENT = "insufficient_data"
VERDICT_BUILD = "build"
VERDICT_CLOSE = "close"
VERDICT_INCONCLUSIVE = "inconclusive"


def cosine(a, b) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 if either is a zero vector."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def entity_values(incident) -> list:
    """The entity strings keyword retrieval matches on — the exact IOC/asset values from
    `precedents._matching_keys`, so query and corpus share one representation."""
    ioc_values, asset_names, asset_ips = _matching_keys(incident)
    return sorted(ioc_values) + sorted(asset_names) + sorted(asset_ips)


def embedding_text(incident) -> str:
    """title + description + entities — the presenting signal available at Classify time,
    embedded symmetrically for query and corpus. Resolution is the *label*, never the key."""
    parts = [incident.title or "", incident.description or ""]
    parts.extend(entity_values(incident))
    return "\n".join(p for p in parts if p).strip()


def corpus_for(incident):
    """Same-org resolved Incidents that existed as precedents at `incident`'s Classify time:
    closed, with a `closure_reason`, concluded before this incident was created. The org
    hard-filter is the ADR-0031 isolation invariant — never relax it.

    Caveat: Incident has no `closed_at`, so "concluded before" is proxied by
    `updated_at < created_at`. Because `updated_at` is `auto_now`, a prior that genuinely
    closed before this incident but was *commented on later* has its `updated_at` bumped
    past the cutoff and is dropped — shrinking the headline denominator toward `both_missed`.
    A disclosed approximation of a research job, not a serving path; if it distorts the
    numbers, that is itself the signal to build the exact live-shadow log."""
    from incidents.models import Incident

    return (
        Incident.objects
        .filter(organization_id=incident.organization_id, state=Incident.STATE_CLOSED)
        .filter(closure_reason__isnull=False)
        .filter(updated_at__lt=incident.created_at)
        .exclude(pk=incident.pk)
        .select_related("subject")
    )


def keyword_hits(incident, corpus, *, top_k=DEFAULT_TOP_K) -> set:
    """Corpus PKs the live keyword `Q` (`build_precedents`) would surface for `incident`,
    same match predicate and same top-K-by-recency budget the real retrieval applies."""
    ioc_values, asset_names, asset_ips = _matching_keys(incident)
    if not (ioc_values or asset_names or asset_ips):
        return set()
    match = _match_q(ioc_values, asset_names, asset_ips)
    ids = (
        corpus.filter(match)
        .order_by("-updated_at")
        .values_list("pk", flat=True)
        .distinct()
    )
    return set(list(ids)[:top_k])


def embedding_hits(incident, corpus_list, embedder, *, top_k=DEFAULT_TOP_K) -> set:
    """Corpus PKs a brute-force cosine ranking would surface in its top-K. `embedder` maps
    a list of texts to a list of vectors (query first, then each corpus incident)."""
    if not corpus_list:
        return set()
    texts = [embedding_text(incident)] + [embedding_text(c) for c in corpus_list]
    vectors = embedder(texts)
    query_vec, corpus_vecs = vectors[0], vectors[1:]
    ranked = sorted(
        zip(corpus_list, corpus_vecs),
        key=lambda cv: cosine(query_vec, cv[1]),
        reverse=True,
    )
    return {c.pk for c, _ in ranked[:top_k]}


@dataclass
class CorrectionOutcome:
    incident_id: int
    display_id: str
    org_id: int
    human_subject: str
    bucket: str
    keyword_ids: set = field(default_factory=set)
    embedding_ids: set = field(default_factory=set)
    prior_ids: set = field(default_factory=set)


def classify_correction(correction, embedder, *, top_k=DEFAULT_TOP_K) -> CorrectionOutcome:
    """Bucket a single subject **Classification Correction**. The embedder is only invoked
    when the keyword retrieval misses (no need to embed a case keyword already covers)."""
    incident = correction.incident
    human_subject_id = correction.human_subject_id
    corpus = corpus_for(incident)
    prior_ids = set(
        corpus.filter(subject_id=human_subject_id).values_list("pk", flat=True)
    )
    keyword_ids: set = set()
    embedding_ids: set = set()

    if not prior_ids:
        bucket = CORPUS_GAP
    else:
        keyword_ids = keyword_hits(incident, corpus, top_k=top_k)
        if keyword_ids & prior_ids:
            bucket = KEYWORD_COVERED
        else:
            embedding_ids = embedding_hits(incident, list(corpus), embedder, top_k=top_k)
            bucket = EMBEDDING_RECOVERED if (embedding_ids & prior_ids) else BOTH_MISSED

    return CorrectionOutcome(
        incident_id=incident.pk,
        display_id=incident.display_id,
        org_id=incident.organization_id,
        human_subject=(correction.human_subject.name if correction.human_subject else ""),
        bucket=bucket,
        keyword_ids=keyword_ids,
        embedding_ids=embedding_ids,
        prior_ids=prior_ids,
    )


@dataclass
class MeasurementReport:
    scored: int                              # qualifying subject corrections classified
    skipped_no_subject: int                  # corrections with no human_subject (excluded)
    buckets: Counter                         # bucket -> count across all scored
    per_org: dict                            # org_id -> Counter(bucket -> count)
    recovered_examples: list                 # CorrectionOutcome for each EMBEDDING_RECOVERED
    min_sample: int
    build_threshold: float
    close_threshold: float

    @property
    def exists_total(self) -> int:
        """Scored cases where the right prior existed at all — the headline denominator."""
        return (
            self.buckets[KEYWORD_COVERED]
            + self.buckets[EMBEDDING_RECOVERED]
            + self.buckets[BOTH_MISSED]
        )

    @property
    def headline(self):
        """Share of *retrievable* corrections that needed semantics: the #657 signal.
        None when no prior ever existed (nothing to decide on)."""
        total = self.exists_total
        if total == 0:
            return None
        return self.buckets[EMBEDDING_RECOVERED] / total

    @property
    def verdict(self) -> str:
        if self.exists_total < self.min_sample:
            return VERDICT_INSUFFICIENT
        h = self.headline
        if h >= self.build_threshold:
            return VERDICT_BUILD
        if h < self.close_threshold:
            return VERDICT_CLOSE
        return VERDICT_INCONCLUSIVE


def run_measurement(
    corrections,
    embedder,
    *,
    top_k=DEFAULT_TOP_K,
    min_sample=MIN_SAMPLE,
    build_threshold=BUILD_THRESHOLD,
    close_threshold=CLOSE_THRESHOLD,
) -> MeasurementReport:
    """Classify every **Classification Correction** in `corrections` and aggregate the
    correction-anchored partition into a pre-registered go/no-go verdict for #657."""
    buckets: Counter = Counter()
    per_org: dict = defaultdict(Counter)
    recovered: list = []
    scored = 0
    skipped_no_subject = 0

    for correction in corrections:
        if correction.human_subject_id is None:
            skipped_no_subject += 1
            continue
        scored += 1
        outcome = classify_correction(correction, embedder, top_k=top_k)
        buckets[outcome.bucket] += 1
        per_org[outcome.org_id][outcome.bucket] += 1
        if outcome.bucket == EMBEDDING_RECOVERED:
            recovered.append(outcome)

    return MeasurementReport(
        scored=scored,
        skipped_no_subject=skipped_no_subject,
        buckets=buckets,
        per_org=dict(per_org),
        recovered_examples=recovered,
        min_sample=min_sample,
        build_threshold=build_threshold,
        close_threshold=close_threshold,
    )
