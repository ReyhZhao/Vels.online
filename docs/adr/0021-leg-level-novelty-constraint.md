# Leg-level Novelty Constraint for Scheduled Search Rules

## Status

accepted

## Context

Operators want to detect a **first-time event** — canonically, "a user logs onto a host that is new *for them*." Every existing **Scheduled Search Rule** axis (count threshold, Diversity Constraint, Absence Firing, time-of-day filter, multi-leg co-occurrence) is confined to a single rolling **Window**; none can answer "have we seen this value *before*?" This is a genuinely new axis — the first that reaches outside one window to compare against history — in the same family as the deliberately-deferred "impossible travel" (geo-distance) and "strict sequence/ordering" axes.

## Decision

Add a **Novelty Constraint** modelled as the baseline-comparing sibling of the Diversity Constraint:

- **`novelty_field` on the Leg** (parallel to `distinct_field`). Its presence makes the leg a novelty leg and names the watched field (e.g. `host.name`). The grouping is the rule's existing **Correlation Key** (e.g. `user.name`) — so "new host for a user" is `correlation_key = user.name`, `novelty_field = host.name`, and the symmetric "new user on a host" is the two fields swapped.
- **`baseline_lookback_days` on the Rule** (parallel to `window_minutes`). The leg owns *what* is watched; the rule owns *time*. Units are days, not minutes, because baselines are intrinsically days/weeks while detection windows are minutes/hours — and the field name documents the intent. Setting it to the index retention ceiling yields the "first time *ever*" variant.

Evaluate it **statelessly, pushed down to OpenSearch**: one terms-of-terms aggregation (`correlation_key` → `novelty_field`) with a `min(@timestamp)` sub-aggregation over `[now − baseline_lookback, now]`. A value is **new** iff its earliest sighting in the baseline lands inside the detection boundary `[now − interval_minutes, now]`.

The "appeared recently" boundary is the **run interval** (`interval_minutes`), *not* `window_minutes`. "First seen since the last run" is gap-free and overlap-free by construction: a window shorter than the interval would silently miss first-logins that occur between runs; a window longer than the interval would re-fire the same old login into a fresh Incident once the prior one closes. `window_minutes` therefore does not apply to a pure novelty leg.

## Considered Options

- **Persisted seen-set table** (`SeenLogin(user, host, first_seen)`): rejected. It reintroduces exactly the per-entity write-model state the pull engine (ADR-0006) was designed to avoid, and it has a cold-start blindspot — a newly-enabled rule starts with an empty table and would flag everything as new (or need a warm-up period to design and explain).
- **Two-query set-difference** (distinct values in detection window minus distinct values in baseline window): rejected. Doubles the queries and needs a boundary correction because the detection window is a subset of the baseline. The min-timestamp formulation makes that subset relationship *correct by construction* rather than something to subtract around.

## Consequences

- **No warm-up.** A novelty rule works on its first run by reading existing index history as its baseline.
- **Self-limiting re-firing.** Once a `(key, novelty value)` fires, on the next run its earliest sighting is in the past (before the new detection window), so it does not re-fire until the value ages out of the baseline.
- **Evidence = novel docs only.** A novelty firing materialises only the documents carrying the *new* `novelty_field` value(s) — not all of the key's window docs (the Diversity path's behaviour). "alice logged onto db-prod-1 for the first time" links the db-prod-1 logon, not her familiar daily logons. This requires the per-key hit-fetch to add a filter on the novel value(s) for novelty legs — a deliberate divergence from the Diversity hit-fetch.
- **Cost.** Each run issues a terms-of-terms aggregation over a long lookback; cost scales with `distinct(correlation_key) × distinct(novelty_field)` cardinality and depends on the `@timestamp` mapping — the same query shape the multi-leg path already issues, but over a longer time span.
- **Honest ceiling.** "First time ever" is bounded by index retention; the baseline cannot see further back than the data retained.
- **Rule Tests need era-spanning timestamps.** A novelty Rule Test (ADR-0010) is meaningless unless its **Sample Documents** can be placed in distinct time eras — a baseline doc (older than the detection boundary, establishing "known") and a detection doc (within the last interval, the novel logon). Sample Documents therefore gain **relative `@timestamp` offsets** (e.g. `now-40d`, `now-5m`) resolved when the ephemeral index is populated, so a test stays valid whenever it runs. A literal `@timestamp` still works; pure count/diversity tests are unaffected.
- A Novelty Constraint is incoherent with an Absence Firing leg (`count_operator = lte`) and should be rejected at save time, like the existing `lte` + correlation-key guard.
- **`novelty_field` is a raw Wazuh field path** (resolved via `.keyword` like the Diversity Constraint's `distinct_field`), not an ECS correlation-key name — so "novelty on host" is authored as `agent.name`, and the builder offers it from the dynamic field catalog (ADR-0007), not the ECS key list.
- **v1 scope: Linux/SSH.** The motivating "first logon" case is grouped on `user.name`, which maps to the single Wazuh field `data.dstuser` — reliable for SSH/PAM auth but *not* Windows interactive logons (`data.win.eventdata.targetUserName`) or `data.srcuser`-style decoders. This is a deliberate scope boundary, not an oversight: broadening the `user.name` mapping across user fields is a separate change, deferred because the fleet is Linux-heavy and Windows lateral movement is not a day-one concern.
