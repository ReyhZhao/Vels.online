# The Hunt general-query escape hatch is a structured aggregation grammar, not restricted DSL

## Status

accepted

## Context

The **Hunt** module ([ADR-0015](0015-threat-hunting-incident-producing-module.md)) ships behavioral hunting as a set of composable **fixed-lens** tools — `top_rules`, `event_histogram`, `top_values` (a hand-curated 8-field allowlist), `agent_activity`, IOC-search-by-hash/ip/domain, and the IT Hygiene Inventory lenses ([ADR-0022](0022-it-hygiene-inventory-tools-state-indices-explicit-recording.md)). This was deliberate for v1: it stayed inside [ADR-0011](0011-assistant-agentic-tool-calling-loop.md)'s reliability guidance for the Ollama runtime (narrow single-purpose schemas), bounded aggregation cost/abuse, and stayed testable.

The known limitation, recorded when v1 landed: the model can only hunt the patterns we anticipated with a lens. Each aggregation lens freezes exactly one shape — `top_values` is a single-level `terms`, `event_histogram` a `date_histogram`, `top_rules` a `terms` on `rule.description` — and the model cannot *compose* them. Real threat hunting needs "failed logins grouped by source IP then by user," "distinct destination ports per source IP," "auth events in subnet X bucketed over time" — none of which any fixed lens expresses. Issue #473 tracked the escape hatch.

Issue #473 framed the escape hatch as "one constrained general-query tool accepting a *restricted OpenSearch DSL*." That phrasing conflicts head-on with **ADR-0007**, which built the Scheduled Search Rule subsystem on the opposite stance: *the analyst and the LLM only ever pick `field / operator / value`, and a type-constrained translator is the only thing that ever emits OpenSearch DSL — so "dynamic" is stricter, not looser, than a frozen list.* We resolve the conflict in ADR-0007's favour: the gap the fixed lenses have is not filtering (ADR-0007's `_condition_to_clause` + `validate_search_field` already cover that) but the *inability to compose a novel aggregation*. So the new expressiveness lives in a **structured, bounded aggregation grammar**, not in DSL the model writes.

This is a **design decision** ahead of empirical usage data: v1 hunt volume is too low to mine for an allowlist, but operators already report the fixed setup is too rigid for real dynamic hunting, so we design the contract now and tune from usage later.

## Decision

- **A structured general-query lens, `search_events` — never raw DSL.** The model supplies a list of `{field, operator, value}` filter conditions (reusing the ADR-0007 `search_compiler`: `validate_search_field` + `_condition_to_clause`, type-aware) plus a small structured aggregation spec. The model never touches OpenSearch syntax. This keeps ADR-0007's "model never emits DSL" invariant intact and makes the feature **injection-safe by construction** — there is no DSL string to inject into; every field is validated against the live mapping and every aggregation choice is enum-constrained.

- **The aggregation grammar:** `filters[]` + `group_by[≤2 fields]` (nested `terms`) + `metric{type: count | cardinality | sum | avg, field?}` + optional `interval{1h | 6h | 1d}` (a `date_histogram` outer bucket). This subsumes `top_values`, `top_rules`, and `event_histogram` as special cases while permitting their composition. Field types are validated against `OpenSearchClient.get_field_mapping()`: `group_by`/`cardinality` fields must be aggregatable (text resolved via `.keyword`, as `_agg_target` already does); `sum`/`avg` fields must be numeric (`_NUMERIC_TYPES`).

- **Aggregation-only — commits no Findings.** `search_events` returns buckets/counts and records nothing, matching `top_values`/`inventory_search` and CONTEXT.md's principle that a bare aggregation match "is not itself proof of compromise." Turning an insight into evidence stays the job of the existing recorders (`agent_activity`, `record_inventory_finding`). The general query is purely an *exploration* instrument.

- **The full dynamic field catalog is the allowlist, not a curated list.** Any field in the live mapping is selectable, gated only by server-side type validation — rebuilding a curated allowlist would just restore the cage #473 exists to remove. The ~3000-field mapping is never dumped into the prompt; a companion **`describe_fields`** grounding tool lets the model discover populated fields/types on demand (agentic-native, per ADR-0011's "tools for expensive/unbounded context"), rather than a per-turn prompt-injected briefing. `describe_fields` exposes index-wide *schema* (field names + types), never per-tenant values, so grounding leaks no tenant data.

- **Bounded cost.** The time window is fixed to the hunt's `lookback_days` (no per-call override). Buckets are clamped — outer `terms` ≤ 50, inner ≤ 20 (defaults 20); the histogram enum bounds time buckets. Depth is capped at 2 `terms` levels (+ optional histogram), consistent with the single sub-agg level of ADR-0009/0021. The `hunt_caps()` per-tool timeout is the final backstop.

- **Strict per-org fan-out.** Like every existing lens, `search_events` issues **one aggregation query per org** over that org's agent ids and returns `by_org` results — it **never** merges into a single cross-tenant aggregation. The general query must not become the one tool that joins across tenants; the tenant-isolation invariant holds by construction.

- **Gated to capable models, with graceful degrade.** `search_events` + `describe_fields` form the largest schema in the system. A new provider capability — `supports_complex_tools()`, mirroring the existing `uses_native_web_search()` and keyed on the same cloud signal — gates their inclusion. On a weak/self-hosted provider the Hunt silently keeps the fixed lenses (the same way it loses web search today), rather than erroring. This satisfies #473's "validate weaker models can drive it, or gate to stronger Cloud models" without an unfunded weak-model reliability prototype.

- **Hybrid is purely additive for v1.** All v1 lenses stay; `search_events` + `describe_fields` are added alongside (≈11 tools on the capable-model path). Although the grammar strictly subsumes `top_rules`/`top_values`/`event_histogram`, we keep them for now: it preserves familiarity, and exposing both paths lets us *observe* whether analysts reach for the grammar or the frozen lenses — generating the empirical signal to retire the redundant lenses later, with evidence rather than a guess.

## Considered Options

- **Structured `field/operator/value` + bounded aggregation grammar (chosen)** — full novel-query expressiveness, reuses the battle-tested ADR-0007 compiler, injection-safe by construction, small enough to gate to capable models.
- **Restricted OpenSearch DSL JSON, parsed/validated server-side (the issue's literal framing)** — more expressive (arbitrary bool/agg trees) but multiplies the injection-validation surface, enlarges the schema exactly where reliability is the stated risk, and directly contradicts ADR-0007's settled "model never emits DSL" stance. Rejected.
- **Curated-subset allowlist (extend `_TOP_VALUE_FIELDS`)** — predictable and token-cheap, but reintroduces the precise limitation #473 exists to remove. Rejected.
- **Dual-mode (return raw hits *and* aggregations, auto-recording Findings)** — most powerful, but enlarges the biggest schema further and reopens the "aggregation match ≠ evidence" concern. Raw-hit retrieval is already covered by `ioc_search`/`agent_activity`. Deferred.
- **Substitutive hybrid (drop the three subsumed lenses when the grammar is active)** — flatter tool count, less redundancy; deferred until usage shows it is safe to retire them.
- **Per-turn prompt-injected field catalog instead of a `describe_fields` tool** — simpler, but is exactly the token bloat ADR-0007 warns against. Rejected in favour of an on-demand tool.

## Consequences

- A new `search_events` lens and a `describe_fields` grounding tool, both reusing `search_compiler`/`get_field_mapping`; the aggregation spec is a new structured grammar the compiler gains (the current compiler emits only flat `terms`/sub-agg shapes).
- The provider interface gains `supports_complex_tools()`; `build_hunt_lenses` becomes capability-aware. Self-hosted Hunts run with the fixed lenses only — a documented degraded mode, like web search.
- The hunt system prompt must teach the model when to reach for `search_events`/`describe_fields` versus the fixed lenses.
- Retiring the three subsumed aggregation lenses is a tracked fast-follow, gated on observed usage. Dual-mode raw-hit retrieval and a paired `record_search_finding` recorder remain deferred options if a gap appears.
- The original #473 inputs ("use v1 telemetry to bound the allowlist") are satisfied differently: the allowlist is the live mapping, and the additive hybrid *produces* the usage signal rather than waiting on it.
