# Scheduled Search Rules use the live Wazuh index mapping as their field catalog, not a curated list

Streaming **Correlation Rule** legs reference a small, hand-curated catalog of app-normalised fields. A **Scheduled Search Rule** matches *raw Wazuh documents*, whose schema is an unbounded namespace of thousands of fields that varies as new Wazuh rules and decoders appear. Hand-curating that catalog would force us to know every useful field up front — yet the whole point of the feature is to catch patterns in alert types we have not seen before. So the **live index `_mapping` is the catalog**: a field is valid if it exists in the mapping with a type-compatible operator, validated server-side at save/compile time. A type-constrained translator is the only thing that ever emits OpenSearch DSL (the analyst and the LLM only ever pick `field / operator / value`), so "dynamic" is *stricter*, not looser, than a frozen list.

## Considered Options

- **Mapping-as-catalog + type-constrained translator + data-sampled grounding (chosen)** — full coverage of any real Wazuh field, with safety from validating against ground truth.
- **Curated static allow-list** (as streaming rules use) — predictable and token-cheap for the LLM, but cannot reference fields we did not bless in advance; rejected because novel Wazuh alert types are exactly what we want to catch.
- **Reflect the mapping but expose all ~3000 fields to the builder/LLM** — drowns the UI and the prompt and invites garbage/expensive queries.

## Consequences

- **The LLM is bounded by grounding, not by a frozen vocabulary.** Drafting is retrieval-augmented and two-pass (v1): a cached **rule catalog keyed on `rule.id`** (representative description + groups + level + seen-count, built from a cheap `terms` agg, TTL'd like the mapping cache) is the menu; the model selects relevant `rule.id`s; we lazily expand *those* rules' populated fields + top values; the model drafts; a mapping-aware sanitiser validates the draft against the full mapping and drops/warns on anything invalid. This keeps tokens bounded while permitting any real field. Agentic tool-calling is deferred (issue #402).
- **`rule.id`, not `rule.description`, is the catalog key** — rendered descriptions are templated with live values and have runaway cardinality.
- **A curated core remains — for semantics, not gating.** Friendly labels, the default field picker, and the `correlation_key → Wazuh path` mapping (e.g. `host.name → agent.name`, `source.ip → data.srcip`) are judgements the mapping cannot supply. Everything outside the core is still reachable.
- Non-aggregatable `text` fields are refused as a `correlation_key`; the translator reads each field's type from the mapping to pick `.keyword` / `range` / ip-range forms.
- Requires a new `OpenSearchClient.get_field_mapping()` plus a cached rule-catalog query, both TTL'd.
