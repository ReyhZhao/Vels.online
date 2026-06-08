# The incident assistant proposes; a human confirms every mutation

> **Superseded by [ADR-0012](0012-incident-assistant-relaxed-action-authority.md).** The blanket "never mutates on its own" rule is relaxed to a risk-graded one: the assistant auto-executes internal, reversible, non-lifecycle actions and proposes everything else. The propose-and-confirm contract below still governs the high-risk action set.

The **incident assistant** is a staff-only, multi-turn conversational LLM interface grounded in a specific incident. It can answer questions about the incident using live server-side context (fields, linked alerts, IOCs, tasks, task templates) and propose a bounded set of actions the analyst can confirm with one click.

## Decision

The assistant follows the same **propose-and-confirm** contract already established for Detection Suggestions ([ADR-0004](0004-llm-residual-safety-net-suggestion-only.md)) and the rule-author assistant ([ADR-0005](0005-rule-author-assistant-ephemeral-stateless.md)):

- The LLM **proposes**; a human **confirms**. The assistant never mutates incident data on its own.
- The conversation is **ephemeral and stateless**: it lives in React client state, is replayed to the endpoint each turn, and disappears when the drawer is closed. Nothing about the dialogue is persisted.
- Grounding is **recomputed server-side every turn** from the live incident record; the client cannot supply or influence it.
- Proposed actions are drawn from a **bounded allowlist** and validated server-side before being presented:
  - `update_field` — one of `severity`, `tlp`, `pap`, `description`, `subject`, `assignee`
  - `transition_state` — constrained to transitions currently legal for the incident's state
  - `apply_task_template` — constrained to templates available for the incident's subject
- Confirming an action calls the **existing** mutation endpoint unchanged (field PATCH, transition, apply-template), so permissions, validation, and side effects are identical to a manual edit.
- Each confirmed action records an `assistant_action` timeline event for audit, in addition to the normal event the mutation endpoint already records.

## Considered Options

- **Autonomous writes** (the LLM mutates directly) — rejected; violates ADR-0004 and removes human oversight. Analysts must remain in the loop for all data changes.
- **Bounded propose-and-confirm (chosen)** — consistent with ADR-0004/0005. Smallest surface; trustworthy because every change goes through the existing validated path.
- **Stateful server conversation** — would allow resuming a session across page reloads; not needed in v1, adds storage and cleanup overhead. Additive later if required.

## Consequences

- Closing the drawer discards the conversation. The only durable artifacts are the incident mutations themselves plus the `assistant_action` timeline events.
- The endpoint (`POST /api/incidents/<id>/assistant/`) is a pure function of `{ messages[] }` plus server-recomputed grounding. It is trivially testable by stubbing the provider.
- Any proposed action that references a non-allowlisted field, an illegal transition, or a template not valid for the incident's subject is rejected server-side and never presented to the user.
- When the LLM provider is unavailable or misconfigured, the endpoint returns a clear 503 and the drawer degrades gracefully.
