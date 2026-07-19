# Detection Scan: primary LLM detector over entity-neighbourhoods

The LLM detection pillar is promoted from a *residual safety-net* to a **primary
LLM detector** — the **Detection Scan** — that finds multi-alert attack patterns
no static **Correlation Rule** authored. It stays **suggestion-only** (ADR-0004's
human-in-the-loop stance is retained in full), but its *scope* changes: where the
safety-net reviewed only the **residual** (alerts no rule promoted or linked), the
Scan reasons over handled alerts too, as read-only context. This **supersedes the
scope decision in [ADR-0004](0004-llm-residual-safety-net-suggestion-only.md)** —
its "reviews *only* the residual" clause — while leaving that ADR's suggestion-only,
never-auto-create, and separate-confidence-threshold decisions intact.

Widening scope reopens the exact cost concern that deferred #300 bullet 1, so the
Scan never reasons over the raw org window. Instead it assembles bounded
**Candidate Neighbourhood**s deterministically from the indexed `AlertEntity`
table ([ADR-0001](0001-ecs-entity-envelope-at-ingestion.md)): for each residual
alert, the other alerts (handled *and* unhandled) sharing **any** ECS entity value
within the window, scoped to one organisation. The LLM reasons one neighbourhood
(or a capped batch) at a time. The entity join only prunes *which alerts might
relate*; whether a neighbourhood is an actual attack stays the LLM's judgement —
so this is not a re-implementation of the human-authored, deterministic rule
engine.

v1 assembles neighbourhoods by **union** — share *any* entity value, rather than
anchoring on one blessed entity type — because at the current low alert volume
union maximises recall and the "noisy-host neighbourhood balloon" is hypothetical.
A hard neighbourhood **size cap** rides along as a safety valve (and the direct
lever on the Ollama token budget), not a tuning knob. If volume grows and
neighbourhoods balloon, the fallback is per-blessed-entity anchoring (the
`Correlation Key` entity set) — a tightening, not a redesign.

Two invariants keep the Scan from colliding with the other two engines:

- **Proposals target nothing that already exists.** A **Detection Suggestion**
  must contain ≥ 1 residual alert; a grouping made entirely of already-handled
  alerts is a duplicate of an incident that already exists and is suppressed. The
  Scan widens the LLM's *context*, never its *output target* — it does not point
  at, relink, or merge existing incidents (that is bullet 1's semantic auto-link,
  deferred).
- **Cross-run dedup mirrors the Firing ledger.** At most one *live* (pending)
  Suggestion per grouping; a *dismissed* Suggestion suppresses re-proposal of the
  same or a subset alert set (a materially larger set — new evidence — may
  re-propose); an accepted Suggestion's alerts become `imported` and leave the
  residual pool. This reuses the static engine's "one live per key / re-fire only
  after closure" model rather than inventing a bespoke one, and is what stops a
  rolling-window periodic batch from spamming the inbox.

Cadence stays a **periodic Celery task**, not per-alert: per-alert LLM calls would
exhaust the Ollama Cloud token budget, and inline detection is the hot-path cost
ADR-0004 already rejected. "Primary" therefore means primary in *coverage* (finds
what the rules cannot), not *latency* (the fast-path and async rule engine remain
the low-latency responders).

Calibration is deliberately **lean**: rely on the existing
`DetectionSuggestion.status`/`confidence` for an aggregate accept/dismiss precision
read, plus a stamp of the producing detector and model/prompt version so later
analysis can separate one model era from the next. A *reusable recurring-pattern
fingerprint* for per-shape auto-create gating is out of scope and deferred to #724.

## Considered Options

- **Primary detector over entity-neighbourhoods, suggestion-only (chosen)** — widens coverage past the residual while pruning cost via the entity envelope; keeps humans in the loop and the rule engine un-raced.
- **Keep the residual-only safety-net** — cheapest, but structurally blind to any alert a rule or the fast-path already handled, so it misses attacks that straddle handled and unhandled alerts (the whole point of #300 bullet 1).
- **LLM over the whole org window, unclustered** — simplest prompt shape, but the unbounded inference cost that deferred #300 bullet 1 returns, and no reuse of the entity infrastructure.
- **Let the Scan point at / merge existing incidents** — realises bullet 1's semantic auto-link, but collides with the supersede machinery ([ADR-0002](0002-correlation-rules-supersede-via-duplicate-of.md)) and can manufacture duplicates; deferred.
- **Flip on confidence-gated auto-create now** — trusts an uncalibrated model to manufacture incidents; ADR-0004's rejection still holds.
- **Per-alert (event-driven) evaluation** — lower latency, but blows the Ollama Cloud token budget and is the inline hot-path ADR-0004 rejected.

## Consequences

- **ADR-0004 is superseded in part** — only its residual-only *scope*. Its suggestion-only stance, never-auto-create default, and separate-confidence-threshold decisions remain in force.
- The Scan depends on [ADR-0001](0001-ecs-entity-envelope-at-ingestion.md): an alert with no populated entity is un-neighboured and invisible to correlation — a known v1 blind spot (patterns sharing no entity value are not detected).
- The Scan must be a **seeded periodic task** with an `INTENDED_PERIODIC_TASKS` entry — the failure mode of #722/#677 (a `@shared_task` that never runs because nothing seeds its `PeriodicTask` row). Whatever task ships here replaces the never-scheduled `run_residual_safety_net`.
- Incidents from accepted Suggestions flow into the existing `enrich_iocs_then_triage` pipeline like any other, unchanged.
- Auto-create remains a config flip, not a rebuild; per-shape gating awaits the #724 fingerprint and real accept/dismiss data.
