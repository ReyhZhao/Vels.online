# A Hunt opens in an interactive Scoping phase before any evidence-committing search

[ADR-0015](0015-threat-hunting-incident-producing-module.md) seeds a **Hunt** from a free-text question (or a report URL) and the orchestrator starts calling lenses *immediately* — a one-shot that takes the seed at face value. A free-text question like "are we exposed to the XYZ ransomware campaign?" carries far more ambiguity than that one shot can resolve (which IOCs, which TTPs, which orgs, which window), so the search is only as good as the unrefined seed. We add a **Scoping** phase: every Hunt now opens in an interactive dialogue where the model grills the staff member (and the staff member corrects the model) to reach a shared understanding *before* the authoritative search runs. Searching starts only on an explicit human gate.

## Decision

- **Scoping is a first-class phase of the persisted Hunt, not a throwaway pre-chat.** It reuses the same `Hunt` aggregate, transcript, and event log — the refinement dialogue *is* part of "who hunted what and why," which is the whole reason ADR-0015 persists Hunts. Two new statuses model it: `scoping` (idle, awaiting the human) and `scoping_running` (a Scoping turn in flight). `running` keeps its ADR-0016 meaning — the evidence-committing search is in flight. Every Hunt (question **and** URL seed) opens here: `created → scoping_running → scoping → [Begin hunt] → running → completed`.

- **The phase boundary is *evidence commitment*, not the toolset.** During Scoping the model has the **full toolset** — web search *and* every Wazuh lens — so it can pull threat-intel and live asset/telemetry context to ask grounded questions. But Scoping turns run with a **non-persisting findings sink** (`record_findings = None`): the recording lenses (`ioc_search`, `agent_activity`) report counts back to the model only and commit **no `HuntFinding`** and therefore propose **no Incident**. The **Searching** phase is defined as the run that commits Findings. This is what keeps "only start the actual search once we agree" true while still letting the model orient itself against real data.

- **The human holds the gate exclusively; the model only signals readiness.** When the model judges it has enough, it calls a structured `propose_hunt_plan` tool (refined question, hypotheses, planned lenses, suggested scope/lookback) that emits a distinct event the UI renders as a **plan card** and uses to light up "Begin hunt." The `scoping → running` transition is *always* a human click ([ADR-0004](0004-llm-residual-safety-net-suggestion-only.md)'s human-in-the-loop principle holds for the act that starts committing evidence). Because the gate is available from turn zero, it doubles as the **skip/one-shot escape hatch** — a user who already knows what they want clicks "Begin hunt" immediately and gets the old ADR-0015 behavior.

- **Scoping can refine scope/lookback, not just the prose question.** Scope *is* part of the question; the plan's `suggested_scope` is surfaced as editable, pre-filled fields at the gate. On confirm we update `hunt.scope_orgs` / `lookback_days` *before* the search turn. Tenant isolation and the cross-org audit story are unaffected: the human confirms the final scope and it is recorded, and refinement only ever **narrows** from the recorded seed.

- **The Searching phase continues the full Scoping transcript** (it is the grounding, per ADR-0015) plus a persisted structured `plan` artifact on the Hunt — not a fresh start from the distilled plan. The model knowing what it already looked at makes the sweep smarter and avoids re-deriving context.

- **Scoping turns reuse the ADR-0016 execution path** — Celery background job + persisted event log + reconnectable SSE — via one parameterized `run_hunt_turn(phase=...)` that swaps the system prompt (grilling vs sweeping), the toolset (adds `propose_hunt_plan`), and the findings sink. One execution path, one event log, one transcript, one SSE consumer — no in-request fork inside the Hunt module.

## Considered Options

- **Keep ADR-0015's one-shot, improve the seed prompt instead** — rejected; no prompt can recover intent the user never stated, and the highest-value refinements (narrow the org scope, pick the TTP family) require a back-and-forth, not a better single seed.
- **A separate ephemeral pre-hunt chat that only emits a refined question string** — rejected; throws away the refinement reasoning (which ADR-0015 says to persist), duplicates the transcript/SSE machinery, and splits a Hunt across two records.
- **Disable lenses during Scoping (pure dialogue / web-only)** — rejected; the staff member explicitly wanted the model to orient against real asset/telemetry data to ask sharper questions. The non-persisting sink gives that without committing evidence.
- **Let the model auto-start the search when "confident"** — rejected; removes the human from the moment evidence starts being committed and makes the experience non-deterministic.
- **Run Scoping turns in-request (ADR-0014 style)** — rejected; forks a second streaming mechanism inside the Hunt module that ADR-0016 deliberately avoided, for a turn that (with web + lens fan-out) isn't actually instant anyway.
- **URL seeds stay one-shot, only questions get Scoping** — rejected in favour of routing both through Scoping: a uniform refine-then-search shape is more predictable, and a fetched report still benefits from "which of these IOCs matter to you?".

## Consequences

- The `Hunt` model gains two statuses (`scoping`, `scoping_running`) and a structured `plan` field; the "is a turn in flight?" guard in `HuntTurnView` widens to `status in (running, scoping_running)`.
- Hunt creation no longer kicks a search turn — it kicks a Scoping turn — and a new "Begin hunt" endpoint performs the gated transition (applying any human scope/lookback edits) and kicks the search turn.
- `run_hunt_turn` grows a `phase` parameter; lenses are unchanged (they already guard `if ctx.record_findings`), so the non-persisting sink is just `record_findings = None`.
- The frontend grows a Scoping conversation surface, a plan card, scope/lookback edit-at-gate controls, and a "Begin hunt" button — reusing the existing reconnectable SSE consumer.
- **Deferred:** a turn-level "stop this question" interrupt (today `Cancel` still means abandon the whole hunt, terminal `cancelled`); and richer URL-seed-specific Scoping prompts.
