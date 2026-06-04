# LLM detection is a suggestion-only safety-net over residual alerts

The LLM-assisted detection pillar complements the static Correlation Rules
rather than replacing them. Static rules handle known patterns deterministically
and cheaply; the LLM then reviews only the **residual** — alerts still `new`/
unlinked, aged past a settle delay, within a lookback window — as a periodic
batch (not inline per-alert). This bounds inference cost (the reason #300 bullet 1
was deferred) and avoids racing the async rule engine over fresh alerts. When the
LLM finds a suspicious grouping it produces a **Detection Suggestion** (proposed
alerts + rationale + confidence) for an analyst to accept or dismiss. For v1 it
**never auto-creates incidents**; a per-org auto-create threshold exists but
defaults to off until precision is observed in practice.

## Considered Options

- **Suggestion-only safety-net over residual (chosen)** — bounded cost, human-in-loop while uncalibrated.
- **Confidence-gated auto-create from day one** — faster, but trusts an uncalibrated model to manufacture incidents.
- **LLM as fuzzy leg-matcher inside every rule** — rejected; LLM call in the hot path, non-deterministic, hard to debug.
- **LLM over every alert inline** — rejected; the cost concern that deferred #300 bullet 1.

## Consequences

- A separate confidence threshold from the post-triage `_CORRELATION_THRESHOLD` (that one scores incident↔incident relatedness, a different stage); the LLM provider abstraction is reused.
- Incidents created from accepted suggestions flow into the existing `enrich_iocs_then_triage` pipeline like any other.
- Flipping on auto-create later is a config change, not a rebuild.
