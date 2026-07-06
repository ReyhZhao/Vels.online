# Triage becomes self-learning: distilled Triage Lessons + retrieved Precedents, learned only from human-ratified outcomes and informing (never firing) future triage

Triage ([ADR-0024](0024-two-stage-triage-classify-then-agentic-work.md)/[ADR-0025](0025-triage-agent-unattended-autonomy-boundary.md)) starts every **Incident** cold, re-deriving dispositions the SOC has already reached on many near-identical past incidents ("a lot of cases are the same as earlier closed ones"). We want Triage to carry that experience forward — **without** letting a machine train on its own guesses or turn a learned heuristic into unattended automation. This ADR is the learning/memory model; the cross-tenant boundary it depends on is [ADR-0031](0031-cross-org-triage-learning-isolation.md).

## Decision

Two complementary memory mechanisms feed the existing Triage harness (grounding + tools + orchestrator):

- **Precedent (retrieval).** At **Classify** time, retrieve similar *resolved* incidents with their `closure_reason`, resolution/closing comments, and *final human-ratified* subject/severity — matched by shared **Entities**/**IOCs** (subject-independent, so it applies *before* a subject is chosen). No new store: the "memory" is the incident history, retrieved well. Reuses the existing candidate-list + LLM-judgement pattern (`find_related_incidents` / `_build_correlation_candidates`), enriched with the resolved-case fields.
- **Triage Lesson (distillation).** A new persisted, distilled disposition heuristic keyed on **Subject** (+ `source_kind`), applied in the gated **Work** phase (where the subject is known). A Lesson **informs** the model's judgement and **never itself authorizes an action** — every action still passes the [ADR-0025](0025-triage-agent-unattended-autonomy-boundary.md) gates. Applicability is free-text the model interprets (subject/`source_kind` are the only structured keys), so a Lesson stays a *prior*, not a fire-like rule.

Learning is deliberately disciplined:

- **Learn only from human-ratified ground truth.** A Lesson's evidence is incidents a *human* closed (human-set `closure_reason`) plus human **Classification Corrections** — **never** the Triage Agent's own unratified `pending_closure` disposition, **never** Classify's false-positive auto-close, **never** stale/`duplicate_of` auto-closes. This severs the self-reinforcement loop where the agent trains on its own mistakes.
- **Proposed → approved.** New/strengthened Lessons land `proposed` and are inert until a **SOC staff** member approves them on a staff-only review queue, with **edit-on-approve** (which is what makes human scrubbing of Global Lessons real). Tenants are entirely outside the loop, consistent with Triage/Hunt/Attack-Map being staff-only.
- **A batched distillation sweep is the single learning engine.** A close/correction only *tags* an incident as evidence; a periodic job clusters recent human closes/corrections by subject + `source_kind`, requires **≥ N (=3)** corroborating cases, checks there is no covering active Lesson, and emits org-tier and (across **≥ K (=2)** distinct orgs) global-tier *proposals*. One pass produces both tiers and is where "≥N", "≥K orgs", and "already covered?" are decided coherently.
- **Self-correcting, not just self-reinforcing.** A human overturning a Lesson bumps `contradiction_count`; at **2** it auto-suspends and re-enters the review queue. Lessons decay/archive after **180 days** unused; at most **5** Lessons are injected per subject (the sweep consolidates near-duplicates).
- **Misclassification feedback loop.** Human **Classification Corrections** are recorded first-class, powering a **Classify-accuracy metric** (initial-vs-final subject agreement over time) and enriching **Precedent** with the corrected outcome so Classify dampens overconfidence. Explicit Classify-tier disambiguation lessons are deferred (#658).
- **No vector store in v1.** Subject is the index for Lessons; Precedent uses entity/IOC + LLM judgement. Semantic retrieval via embeddings is deferred (#657).

The lifecycle thresholds (N, K, contradiction limit, decay, injection cap) are **global constants** tuned centrally by the SOC — not per-org knobs — because lesson lifecycle is a property of the SOC's fleet-wide learning process, not a per-tenant risk appetite (unlike `triage_fp_threshold` / `triage_work_threshold`).

## Considered Options

- **Retrieval (Precedent) + distilled store (Lesson), split Classify/Work (chosen)** — Precedent gives Classify concrete "same as last time" grounding cheaply and subject-independently; Lessons capture cross-case generalizations where a single precedent can't, applied where the subject is known. Together they deliver self-learning with full auditability (every memory traces to real, human-closed incidents).
- **Retrieval only (no distilled store)** — simpler and poison-free, but never captures a generalization that is not recoverable from any single past incident. Kept as the always-available floor (Precedent), but insufficient alone for the recurring-pattern value.
- **Structured Lesson predicates (a rule engine for guidance)** — precise and machine-filterable, but makes a Lesson *fire-like*, duplicates the **Correlation Rule** engine, and breaks the "a Lesson informs, it does not fire" framing. Rejected.
- **Learn from the agent's own dispositions** — maximally self-learning, but reinforces the agent's own errors with no human ground truth. Rejected as the core poisoning risk.
- **Embeddings / vector store for retrieval** — deferred (#657): the per-org resolved corpus is small and entity/keyword + LLM judgement suffices; a vector DB + embedding provider + backfill is heavy infra for marginal precision.
- **Per-org lesson approval by the tenant** — gives customers control, but drags org members into an internal SOC mechanism they are not equipped to run. Rejected; approval stays SOC-staff.

## Consequences

- New `TriageLesson` store, a batched distillation task, a staff-only Lesson review queue, a Classify-accuracy metric, and first-class **Classification Correction** recording.
- Precedent enriches the Classify grounding; Lessons enter the Work seed plus a retrieval tool for deeper mid-loop digging.
- Spend rises modestly: Precedent shaping at Classify (cheap DB + existing correlation call), a periodic sweep LLM cost, and capped Lesson tokens at Work.
- A wrong Classify subject is contained downstream — Work only reaches `pending_closure`, a human ratifies, and the ADR-0025 action gates still hold — while the correction loop reduces its recurrence over time.
- CONTEXT.md gains **Triage Lesson**, **Precedent**, and **Classification Correction**; the cross-org tier's tenant-isolation guarantees are [ADR-0031](0031-cross-org-triage-learning-isolation.md).
