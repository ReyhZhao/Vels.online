# Cross-org triage learning crosses tenants only through scrubbed, human-approved Global Lessons — raw cases never cross

The self-learning Triage memory ([ADR-0030](0030-self-learning-triage-memory.md)) wants the SOC's experience to benefit the whole fleet — a small tenant should inherit lessons the SOC learned elsewhere — but the platform's foundational **tenant-isolation invariant** forbids one tenant's raw data entering another tenant's context. These pull in opposite directions. This ADR draws the single permitted channel, analogous to how [ADR-0017](0017-shared-infrastructure-pseudo-org-for-agentless-hunting.md) carves the one deliberate exception for shared-perimeter data.

## Decision

- **Precedent (raw retrieval) is strictly per-org.** Similar resolved incidents are retrieved **only** from the *same* **Organization**'s history. A tenant's raw incidents — real hostnames, IPs, comments — are never surfaced into another tenant's triage context. Retrieval hard-filters on the incident's `organization`; there is no cross-org raw path anywhere.
- **The Global Lesson is the *sole* cross-tenant channel**, and it carries only **generalized prose**: no tenant-specific selectors, values, or identifiers. Its evidence-incident links are **staff-only** — when a tenant's triage applies a Global Lesson, that tenant sees the guidance but never the cross-tenant evidence behind it.
- **Cross-tenant learning is always human-approved and human-scrubbed.** A Global Lesson is either staff-authored, or a system-proposed generalization of a pattern recurring across **≥ K (=2)** distinct orgs; either way a SOC staff member **edits and approves** the final text before it goes active. The human approval — *not* the automated scrubber — is the isolation guarantee.

This mirrors the **System Rule** / **Org Rule** tiering (`organization = null` ⇒ fleet-wide, curated centrally, per-org apply): a Global Lesson is to a Triage Lesson what a System Rule is to an Org Rule.

## Considered Options

- **Per-org lessons only** — dead safe, zero leakage surface, but each tenant re-learns from scratch and smaller tenants never benefit from the SOC's fleet-wide experience — discarding the platform's single greatest asset (seeing the same attack across every tenant). Rejected.
- **Global via raw cross-org retrieval** — surfaces one tenant's real case data into another's context. A direct violation of the tenant-isolation invariant. Rejected outright.
- **Auto-promoted global lessons (LLM scrub, no human)** — fast, but makes an automated scrubber the sole thing standing between one tenant's raw data and another's context, with no backstop. Rejected: a human approver is the guarantee, and the scrubber is only an assist.

## Consequences

- Precedent retrieval carries an unconditional `organization` filter; a code path that could surface a cross-org raw incident is a tenant-isolation bug, not a feature toggle.
- Global Lesson proposal includes a scrub/generalize step, and evidence links are gated staff-only on every surface (review queue, incident "why did the agent think this?" affordances).
- The deferred embedding index (#657) must preserve this boundary: it may not become a backdoor that surfaces raw cross-tenant cases via similarity.
- CONTEXT.md's **Precedent** (per-tenant) and **Triage Lesson** (two-tier) entries encode this split; a future reader must not "optimise" Precedent into a cross-org search.
