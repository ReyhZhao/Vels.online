# The incident assistant may auto-execute internal, reversible, non-lifecycle actions; everything else it proposes

[ADR-0008](0008-incident-assistant-propose-and-confirm.md) held that the incident assistant *never* mutates incident data on its own — it proposes, a human confirms every change. With the agentic tool-calling loop ([ADR-0011](0011-assistant-agentic-tool-calling-loop.md)) the assistant can now *act* within a turn. We relax ADR-0008's blanket rule to a **risk-graded** one rather than keep every action behind a confirmation click. **This ADR supersedes ADR-0008.**

## Decision

Actions are split on two axes — **is it externally visible?** and **does it change the incident's lifecycle / severity / disclosure?** An action is **auto-executed** only when the answer to both is *no*; otherwise it remains a **proposal** the analyst confirms.

- **Auto-execute (internal, reversible, non-lifecycle):** add an internal (staff-only) comment, self-assign, add a tag, link an already-known asset. The model invokes these as tools in phase 1; the orchestrator executes them.
- **Propose (external OR lifecycle/severity/disclosure):** state transitions, `update_field` (severity, TLP, PAP, subject, assignee, description), `apply_task_template`, `send_contact_message`, exception creation, close. These come out of the phase-2 envelope and require a human confirmation click, exactly as under ADR-0008.

Guardrails that make the autonomy safe:

- **No backdoor.** Auto-executed actions call the *same* mutation service the manual UI and the propose-and-confirm path call — identical permissions, validation, and side effects.
- **Always audited.** Every auto-executed action records a timeline event marked **assistant-initiated (autonomous)**, distinct from the `assistant_action` event recorded when a human confirms a proposal, so the audit trail shows who (or what) acted.
- **Loop-bounded & idempotent-guarded.** The orchestrator caps how many auto-actions a single turn may take and guards against runaway repeats (e.g. the same comment twice), so an agentic loop cannot spam mutations.

## Considered Options

- **Risk-graded auto-execute (chosen)** — convenience for the safe, reversible majority of nudges while every consequential or outward-facing change keeps human oversight. Clear, explainable boundary.
- **Keep ADR-0008 unchanged (propose everything)** — safest, but every trivial internal note needs a click; the assistant cannot meaningfully "act."
- **Minimal: auto-execute internal comment only** — the smallest step beyond ADR-0008; rejected for v1 as too timid given self-assign/tag/link are equally low-risk, but it is the obvious fallback if the audit story proves shaky.
- **Full agentic execution (any action a tool)** — maximal autonomy, but reverses the human-in-the-loop principle behind ADR-0004/0005/0008 for the highest-consequence actions; rejected.

## Consequences

- The conversation stays ephemeral, but the incident record can now change mid-conversation without an explicit confirmation for the auto-execute set — the audit timeline is the durable record of what the assistant did.
- A new autonomous-action audit event type and per-turn action guards are required.
- The boundary is data-driven: classifying a *new* action requires deciding which side of the two axes it falls on; externally-visible or lifecycle-affecting always defaults to propose.
- CONTEXT.md's "_Avoid_: autonomous writes" guidance is narrowed: autonomy is permitted but bounded; it is not open-ended.
