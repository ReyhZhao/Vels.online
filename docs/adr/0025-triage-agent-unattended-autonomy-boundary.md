# The Triage Agent acts unattended under a confidence gate — exceeding the human-gated Incident Assistant

The Triage **Work** phase ([ADR-0024](0024-two-stage-triage-classify-then-agentic-work.md)) runs the shared agentic loop on a high-confidence Incident **with no human present**. Every prior autonomy decision in the system assumed a human *was* present to confirm: [ADR-0008](0008-incident-assistant-propose-and-confirm.md) (propose-and-confirm), [ADR-0012](0012-incident-assistant-relaxed-action-authority.md) (auto-execute only internal/reversible/non-lifecycle; propose the rest), [ADR-0013](0013-incident-assistant-works-manual-tasks.md) (assistant works manual tasks but **never** runs `automated`/`wazuh_response` tasks and **never** closes a task). The Triage Agent cannot "propose" — a proposal with nobody watching just languishes. So its boundary must be drawn on **confidence**, not on a confirmation click. This ADR draws that boundary. It **does not supersede** ADR-0012/0013 (which still govern the human-present Incident Assistant); it defines a *different* authority for a *different*, unattended actor, and in doing so deliberately relaxes ADR-0013's blanket "never autonomously touch live infrastructure" for this actor only.

## Decision

The Triage Agent runs only on `disposition_confidence ≥ org.triage_work_threshold` with a matched subject, and within that gate may act autonomously as follows.

**Auto (within the gate):**
- **Apply the playbook** — the model *selects* the matched subject's task template(s) and calls `apply_task_template` as an **executed write** (for the Incident Assistant the same action is a proposal).
- **Work manual tasks** — research each and record findings as a task-scoped internal comment, exactly as ADR-0013 allows. It **never closes** a task; completion stays the human's judgement.
- **Set severity / subject / state**, as today's triage already does.
- **Run `automated` (Semaphore) tasks** — unconditionally on the gate, with **no per-automation flag**. The SOC authors the automation catalog and treats it as safe to fire unattended.
- **Run a `wazuh_response` task** — **only** if that catalog entry is **autonomous-response approved** (a new, default-off `autonomous_triage_approved` flag on `WazuhActiveResponse`, distinct from the existing human-facing `requires_confirmation`). This is the single gate that lets host-isolation / IP-block fire with no human. The flag is **global per response** (not per-org, not per-template-item): an approved response may auto-fire on any tenant's estate, so it is approved only when safe fleet-wide.
- **Notify the incident's contacts** (`send_contact_message`, LLM-written) and **escalate** (bump severity / page). These are outward/lifecycle actions the assistant only proposes; they are permitted here because contact-notification is already automated elsewhere (closure messages) and escalation errs toward *more* human attention.

**Never auto (left to the routed human):**
- **Create detection exceptions** (silences future detections).
- **Close the Incident.** Only the **Classify** phase auto-closes, and only false positives. Closing a real, worked Incident is the human's ratification.

**Guards that make the autonomy safe:**
- **No backdoor.** Every action calls the same service the manual UI / assistant call — identical permissions, validation, side effects — and is tenant-scoped to the Incident's organisation.
- **Always audited.** Each action records an assistant-initiated (autonomous) timeline event (`actor=None`), so the timeline is the durable record of what the agent did.
- **Idempotent across re-runs via the task lifecycle, not new storage.** The run-task tool fires a task only in `state=new`; an already-executed `automated`/`wazuh_response` task sits in `in_progress`/`done` and is skipped, so a manual re-trigger re-researches but never re-isolates. `apply_task_template`'s existing active-task guard prevents re-applying a playbook.
- **Loop-bounded** by ADR-0024's caps and the orchestrator's per-turn auto-action cap and duplicate-skip.

**Hand-off.** On finishing, the agent routes to on-call and lands the Incident in `in_progress` (work remains) or a new **`pending_closure`** state (threat contained — automated/`wazuh_response` ran, research recorded — only human ratification of open manual tasks remains). `pending_closure` is reopenable and is never reached by auto-close.

## Considered Options

- **Confidence-gated autonomy with a pre-authorized destructive set (chosen)** — speed where the model is sure, while the single most dangerous capability (host isolation / IP block) stays behind a deliberate, default-off, curated allowlist. Trusted internal automation flows freely; outward actions are limited to the two that are already-automated or attention-increasing.
- **Mirror ADR-0012/0013 exactly (propose the risky set)** — safest, but "propose" is meaningless with no human in the loop; the proposals would queue unworked and the feature's entire point (act now, fast) evaporates.
- **Full autonomy on high confidence, no per-response flag** — fastest, but lets an uncalibrated model isolate hosts and block IPs across tenants with nothing but a confidence score between it and the customer's production estate. Rejected as reversing the human-in-the-loop principle for exactly the actions it exists to protect.
- **Per-org or per-template-item approval granularity** — finer control, but scatters a safety-critical authorization across many rows (easy to get wrong) or couples it to playbook authoring. Rejected for v1 in favour of one global, auditable per-response flag.
- **A dedicated dedupe ledger for destructive actions** — explicit, but the task-state guard already prevents double-fire without new storage.

## Consequences

- New `autonomous_triage_approved` boolean on `WazuhActiveResponse` (default off), surfaced in the response-catalog admin and clearly separated from `requires_confirmation` so the two are never conflated.
- New `pending_closure` Incident state: transitions (`in_progress`/`on_hold → pending_closure`, `pending_closure → {closed, in_progress}`), membership in `REOPEN_STATES`, and every state-switching site + the UI must handle it.
- The audit/timeline story must clearly mark Triage-Agent-initiated autonomous actions, including infra actions, so an operator can answer "what did the robot do, and to whom?" after the fact.
- The global per-response flag means curating the catalog is a fleet-wide safety act; documentation and the admin UI should make the blast radius explicit at the point of approval.
- CONTEXT.md's autonomy guidance is now actor-specific: the Incident Assistant remains bounded by ADR-0012/0013; the Triage Agent is bounded by *this* ADR. "The LLM auto-runs infra" is true **only** for the Triage Agent, **only** within the confidence gate, and **only** for approved responses (for `wazuh_response`).
