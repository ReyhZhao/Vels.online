# Triage becomes two-stage: a cheap classify, then a confidence-gated agentic work phase

Today **Triage** ([CONTEXT.md](../../CONTEXT.md) → Triage) is a single, unattended model call that fires on every new **Incident** (`run_incident_triage`): it classifies, clamps severity, sets the subject, auto-closes obvious false positives, and otherwise transitions to `triaged` and routes to on-call. It never *investigates* and never *acts on the playbook* — a human picks the Incident up cold. We want Triage to do the obvious work itself when it is confident, so an analyst inherits a worked Incident rather than a blank one — while keeping the cheap, high-volume path cheap.

## Decision

Split Triage into two phases.

- **Classify (always runs).** The existing single-shot call, unchanged in spirit but extended to emit a new **disposition confidence** alongside the existing **false-positive confidence** (and severity/subject/action recommendations). It auto-closes as a false positive by **either** of two paths: high false-positive confidence alone (≥ the org's `triage_fp_threshold`, regardless of the recommended action), **or** the model explicitly recommending closure (`primary_action == close_as_false_positive`) with false-positive confidence at or above a lower per-org floor, `triage_fp_close_bar`. The floor lets an incident the model itself judges to be junk close below the blanket threshold, while still guarding against a low-confidence close recommendation. Nothing else about the cheap path changes; one model call per Incident in the common case.
- **Work (gated).** A new agentic phase runs **only** when `disposition_confidence ≥ org.triage_work_threshold` **and** the Classify phase matched a **subject** (so a **playbook** exists). It reuses the shared agentic orchestrator (`assistants/orchestrator.run_research_phase`, ADR-0011) — the same loop behind the **Incident Assistant** and **Hunt** — to research and then act on the Incident. Its authority and action ceiling are the subject of [ADR-0025](0025-triage-agent-unattended-autonomy-boundary.md).

Supporting shape:

- **Disposition confidence is a positive, distinct signal**, not the inverse of false-positive confidence: an Incident can be clearly-not-junk (low FP) yet still ambiguous to classify (low disposition). Two thresholds, two knobs (`triage_fp_threshold` already exists; `triage_work_threshold` is added per-org, defaulting conservative).
- **The Work phase is a background Celery job with hunt-style relaxed caps** (≈15 iterations / ≈300s / 15s per tool), not the synchronous/SSE path of the Incident Assistant. Nobody is watching at triage time, so there is no live stream; the run is recorded through existing audit (per-action autonomous timeline events, an AI-triage summary comment carrying the tool-trace and a "what remains" note). The loop works as much of the playbook as fits the budget, then hands off — no auto-continue.
- **Automatic run is once per Incident**, guarded by a durable marker so Celery retries of Classify and later-linking alerts never silently re-enter Work. The existing staff-only manual triage button (`IncidentTriageView`) remains the human's deliberate re-trigger and bypasses the marker.
- **Both phases reuse the existing provider abstraction and pipeline.** Classify keeps the existing correlation search (`find_related_incidents`); Work reaches the same data through tools.

## Considered Options

- **Two-stage: cheap classify, then gated agentic work (chosen)** — keeps the high-volume path one cheap call, spends the expensive agentic loop only where confidence says it will pay off, and gives a clean place to draw the autonomy line (the gate). The confidence gate is the single lever operators tune.
- **Replace classify with a single always-on agentic loop** — every Incident, including the flood of low-value ones, pays for a multi-step tool loop; classification becomes the synthesis phase of one run. Rejected: cost scales with alert volume, not with the incidents worth working, and there is no cheap escape hatch for the obvious-junk majority.
- **Keep single-shot classify; bolt task-working on as a separate always-on worker** — simpler to reason about per-stage, but runs the expensive phase unconditionally and loses the "confidence unlocks autonomy" framing the whole feature rests on.
- **Make triage interactive/streamed like the Incident Assistant** — rejected: triage fires seconds after Incident creation, before any analyst is present; a live stream nobody watches is cost with no benefit. The Incident Assistant already covers the human-in-the-loop case.

## Consequences

- The Classify prompt/parser gains a `disposition_confidence` field; `Organization` gains a `triage_work_threshold` knob beside `triage_fp_threshold`, plus a `triage_fp_close_bar` floor (default below `triage_fp_threshold`) for the recommendation-gated close. The AI-triage comment records which gate drove the outcome (`auto_close_reason`: `threshold` / `recommendation` / null) so a closure — or a deliberate non-closure despite a close recommendation — is auditable rather than silent.
- A durable per-Incident "work has run" marker is required (a flag/timestamp), distinct from the transient cache lock that already serialises triage.
- Latency and LLM spend rise **only on the gated path**; the low-confidence majority is unchanged. Spend now scales with the count of high-confidence, subject-matched incidents.
- The Work phase is unattended and *acts* — its authority, the destructive-action guards, and how it hands off are deliberately deferred to [ADR-0025](0025-triage-agent-unattended-autonomy-boundary.md) so the execution model and the authority model can be reasoned about separately (as ADR-0011 and ADR-0012 are for the assistant).
- "Triage" in CONTEXT.md is now a two-phase concept (**Classify** + **Work** / **Triage Agent**); a future reader must not conflate the always-on cheap phase with the gated agentic one.
