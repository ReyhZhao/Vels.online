# The LLM rule-author assistant is ephemeral and stateless

The natural-language **rule-author assistant** lets staff describe a detection in
words and have an LLM draft a **Correlation Rule** (legs, conditions, correlation
key, window, severity) into the existing rule builder for review, refinement, and
save. Unlike its sibling the **Detection Suggestion** — which is a persisted model
with a `pending → accepted/dismissed` lifecycle and an inbox (see [ADR-0004](0004-llm-residual-safety-net-suggestion-only.md)) —
a **Rule Draft** is **not persisted at all**: there is no `RuleDraft` model. The
drafting endpoint (`POST /api/correlations/draft/`) is a pure function of
`{ scope, messages[], current_draft }`; the multi-turn refinement conversation
lives in client (React) state and is replayed each turn; the **grounding** payload
(vocabulary + values + sample records pulled from the scope's recent alerts) is
**recomputed server-side every turn** so the alert data the model sees is always
fresh and trustworthy rather than echoed through the client. Nothing durable
exists until the human saves a real Correlation Rule via the existing staff-gated
`POST /api/correlations/rules/`.

The asymmetry with Detection Suggestion is deliberate, not an oversight: a Rule
Draft is **pre-commit scaffolding** a human is actively shaping toward a save in a
single sitting, whereas a Detection Suggestion is a **durable work item** sitting
in an analyst's queue awaiting an asynchronous yes/no. Different lifecycles justify
different persistence.

## Considered Options

- **Ephemeral + stateless (chosen)** — no model, client-held conversation, server-recomputed grounding. Smallest surface; preserves "the LLM drafts, a human reviews and saves."
- **Persist a `RuleDraft` with a lifecycle** (mirroring Detection Suggestion) — only earns its keep if drafts must survive a reload, be queued, or be audited; none of which v1 needs.
- **Stateful server conversation** — would let a drafting session resume later, at the cost of server-side conversation storage and cleanup.

## Consequences

- Closing the drawer discards the conversation; the saved **rule** is the only artifact. There is no draft history or audit trail of the dialogue.
- The endpoint stays trivially testable (stub the provider) and horizontally stateless.
- Adding persistence later is **additive** (introduce a model, keep the stateless endpoint as the create path), so this choice is cheap to revisit if a "resume/audit drafting" need appears.
- Two entry points share one drafting drawer: a "Draft with AI" action in the staff Correlation Rules admin (scope picked first), and a staff-only "Codify as rule" action on a Detection Suggestion (scope pre-set to that org, first turn auto-run from the suggestion's alerts + rationale).
