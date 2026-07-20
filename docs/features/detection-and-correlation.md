# Detection & Correlation

How signals get into the platform and how individually-unremarkable events are turned into incidents. Covers the [Alert Ingestion Pipeline](#alert-ingestion-pipeline), the streaming [Alert Correlation Engine](#alert-correlation-engine), the pull-based [Scheduled Search Rules](#scheduled-search-rules) engine, and [Rule Tests](#rule-tests).

See also: [Architecture overview](../architecture.md) · [Alert Ingestion API contract](../alert-ingest-contract.md).

---

## Alert Ingestion Pipeline

A pre-incident layer that records every detection before it becomes an incident.

- **Alert inbox** — every external detection lands as an `AL-NNN` Alert record, visible at `/alerts/`, regardless of whether a matching incident already exists. No detection is silently discarded.
- **Smart auto-routing** — high and critical severity alerts with no matching open incident auto-promote to new incidents immediately; low and medium alerts sit in the inbox for analyst review.
- **Duplicate suppression** — incoming alerts are matched against open incidents by Wazuh rule ID or rule description within a configurable lookback window; matches auto-link to the existing incident instead of creating a duplicate.
- **Asset threshold promotion** — sustained low-severity alerts against the same asset within a configurable time window auto-promote to a new incident even when individual severities are low.
- **Bulk promote** — select multiple alerts from the inbox and promote them to a single incident in one action; a preview modal shows the auto-derived incident fields before writing.
- **Linked Alerts panel** — every incident shows a collapsible panel listing all `AL-NNN` records behind it, with state badges and timestamps.
- **Alert enrichment passthrough** — third-party tools (N8N, webhooks) can pass `title`, `description`, `severity`, `pap`, and `tlp` at ingestion time; promoted incidents inherit these values instead of auto-derived placeholders.
- **Source kinds** — alerts can be tagged as `wazuh`, `inbound_email`, `workflow`, `external_source`, `scheduled_search`, or `threat_hunt` so the origin of every detection is visible and filterable.
- **Per-org thresholds** — configure the auto-promote count, time window, and match lookback window per organisation in settings.
- **Delete alert** — individual alerts can be removed from the inbox when they are noise or duplicates that should not be promoted.
- **Create correlation rule from selection** — select one or more alerts and open the rule-author assistant pre-seeded with those alerts as grounding context, turning a recurring signal into a permanent Correlation Rule in one step.

---

## Alert Correlation Engine

Detect multi-step attack patterns from individually-unremarkable signals — without reading every raw alert.

- **ECS entity envelope** — every ingested alert carries a normalised ECS entity envelope (`host.name`, `source.ip`, `user.name`, `file.hash.sha256`, `process.name`). Values are canonicalised on ingest (case-folding, domain stripping) so cross-source entities join correctly. Stored in an indexed `AlertEntity` table for fast window joins.
- **Correlation Rules** — SOC-authored rules define one or more **Legs** (AND-ed field predicates) that must all be satisfied for the same **Correlation Key** value within a rolling **Window**. When every leg fires, the engine raises a single incident at a rule-defined severity with all matching alerts attached as evidence. Semantics are unordered co-occurrence (all-of-N, not a sequence).
- **Per-leg operators** — `equals`, `in [list]`, `contains`, severity `≥/≤`, and IP/CIDR match across alert fields, ECS entities, and selected Wazuh `source_ref` keys (`rule_id`, `rule_description`, `level`, `cve_id`).
- **Correlation keys** — bind legs by `host.name`, `source.ip`, `user.name`, or `none` (for absolute-count threshold rules that do not require a shared entity).
- **Dedup and re-linking** — at most one live firing per `(rule, entity_value)` while the incident is open. Subsequent matching alerts link into the existing incident; a new incident is only raised after the prior one closes.
- **Supersede** — when a correlation fires over alerts already promoted by the simpler fast-path, the engine relinks those alerts to the richer chain incident and marks the simpler incident as a duplicate. Active-work guard rail: incidents `in_progress` or actively assigned are never auto-superseded.
- **System rules** — rules with no org assignment apply as baseline detections to every tenant automatically; they are authored once by Polaris SOC staff and propagate on the next evaluator run.
- **Per-org mutes** — admins can mute any system rule for a specific tenant from the Org Management UI. Muting stops that rule evaluating for the tenant only, without removing it globally.
- **LLM residual safety-net** — a periodic batch task reviews *residual* alerts (unlinked, past a settle delay) and groups related signals using the LLM into **Detection Suggestions**. Each suggestion shows the rationale, confidence score, and the contributing alerts.
- **Detection Suggestion review** — pending suggestions surface in the alert inbox. Accepting a suggestion promotes the grouped alerts into a new incident (entering the full IOC-enrichment and triage pipeline); dismissing removes it from the queue. Auto-creation defaults to off so the LLM never manufactures incidents without analyst approval.
- **Admin rule-builder UI** — a leg-builder drawer lets staff create and edit Correlation Rules visually: add legs, set field/operator/value per condition, choose the correlation key, window, severity, and enabled state. No code editing required.
- **Rule-author assistant** — describe a detection in plain language; the LLM drafts a Correlation Rule (legs, conditions, key, window, severity) grounded in the *actual* alert corpus for the chosen scope (a specific org or all orgs). The draft is pre-filled into the builder for review; the assistant never activates a rule.
- **Alert-grounded drafting** — before drafting, the assistant samples the real alert corpus (source kinds present, entity types, rule IDs and titles, severity mix) so proposed fields and values genuinely exist in the data.
- **Conversational refinement** — after the initial draft, analysts can iterate in a multi-turn chat to tighten conditions, change the correlation key, or adjust the window before saving.
- **Web-search grounding** — the rule-author assistant shares the agentic tool-calling loop and can search the internet about a threat it is asked to detect, so the rule it drafts reflects how the threat actually manifests in the wild.
- **Scope selection and ownership** — drafting for a specific org defaults the rule to an Org Rule; drafting against all orgs defaults to a System Rule.
- **Codify as rule** — a Detection Suggestion has a "Codify as rule" action that opens the rule-author assistant pre-seeded with the suggestion's context, turning a recurring LLM-flagged pattern into a permanent durable rule.
- **Create correlation rule from selected alerts** — select one or more alerts in the inbox and open the rule-author assistant pre-populated with those alerts as grounding context.

---

## Scheduled Search Rules

Pull-based detection over the full Wazuh OpenSearch data stream — without ingesting every event into the platform.

- **Pull model** — unlike the streaming engine, Scheduled Search Rules push their query *into* the Wazuh OpenSearch backend on a schedule. Only when the pattern is matched do the relevant documents get pulled in as **Findings** (materialised Alerts) and grouped into one Incident. The full Wazuh stream stays in OpenSearch.
- **Same leg/condition builder** — Scheduled Search Rules use the identical leg, condition, correlation key, and window model as Correlation Rules, so analysts learn one mental model for both engines.
- **Dynamic field catalog** — the platform pulls the live OpenSearch index mapping (TTL-cached) to populate field choices. Operators and values are validated against the real mapping so analysts cannot save a rule that references a non-existent or wrongly-typed field.
- **Multi-leg co-occurrence** — multi-leg rules require all legs satisfied for the same correlation-key value within the window; the evaluator uses per-leg `terms` aggregations and a Python join, keeping query cost bounded.
- **Diversity Constraint** — an optional `distinct_field` + `min_distinct` on a leg fires only when a correlation key spans *N or more distinct values* of a secondary field within the window (impossible-travel-lite — e.g. the same `user.name` seen from ≥2 distinct `GeoLocation.country_name` values). It uses a `terms` sub-aggregation so the raised incident can name the actual values and their counts, and it composes inside multi-leg rules. The builder enforces a real correlation key, `min_distinct ≥ 2`, and an aggregatable `distinct_field` distinct from the key.
- **Novelty Constraint** — the baseline-comparing sibling of the Diversity Constraint: an optional `novelty_field` on a leg fires only the *first time* a correlation-key value is seen with a given secondary value across a rule-level `baseline_lookback_days` history — canonically "a user logs onto a host that is new *for them*" (`correlation_key = user.name`, `novelty_field = host.name`). It is the first axis that reaches outside a single window to compare against history. Evaluation is stateless and pushed down to OpenSearch (a terms-of-terms aggregation with a `min(@timestamp)` sub-aggregation): a value is novel iff its earliest sighting in the baseline lands inside the latest run interval — so there is no warm-up period and no per-entity seen-set table to maintain. A novelty firing materialises only the documents carrying the *new* value (the first `db-prod-1` logon, not the user's familiar daily logons). Setting the lookback to the index-retention ceiling yields the "first time *ever*" variant. v1 is scoped to Linux/SSH auth (`user.name` → `data.dstuser`).
- **Absence Firing (dead-man's-switch)** — each leg carries a **Count Operator**: `gte` (default — the existing "at least N matched" behaviour) or `lte` (the inverse). An `lte` leg fires when *too few* — typically zero — documents matched within the window, catching expected signals that went silent (e.g. "no firewall logs received in the past hour"). An Absence Firing raises a **zero-Alert Incident** directly — the shortfall (window, expected vs actual count, the absent condition) is recorded in the incident description and a `SearchFiring` ledger row rather than fabricating a synthetic Alert. It reuses the same one-live-incident-per-`(rule, key)` dedup and the normal IOC/triage pipeline; v1 supports `correlation_key = none` only (single-leg).
- **Time-of-day window** — a rule can restrict matching to a recurring time-of-day range (e.g. outside 08:00–18:00), so events that are normal during business hours — like an admin login to a firewall — only raise an incident when they occur off-hours.
- **Schedule lifecycle** — each rule gets its own `django-celery-beat` `PeriodicTask` (minimum 5-minute cadence). The schedule is created, updated, or deleted automatically whenever the rule is saved or removed — no manual Celery configuration needed.
- **Run state inline** — the rules admin table shows each rule's last-run time, next-run time, and total run count so operators know the rule is healthy at a glance.
- **Per-rule firing summary** — the admin table tracks whether, when, and how many times each rule has actually raised an incident, so operators can see at a glance which rules are live and earning their keep versus sitting silent.
- **Run now** — a per-rule "Run now" button dispatches the evaluator immediately for ad-hoc testing without waiting for the schedule.
- **Clone rule** — duplicate an existing rule (legs, conditions, key, window, schedule) into a new draft as a starting point for a variant, instead of rebuilding it by hand.
- **Debug unsaved rules** — the create/edit drawer can run the evaluator against the *current, unsaved* form values, so analysts can tweak legs and conditions and immediately see what would match before committing the rule — the same debug interface used for saved rules, applied to ad-hoc edits.
- **Run history** — each rule's run history (status, duration, errors) is accessible from the admin UI for debugging failing rules.
- **Dedup and idempotency** — `SearchFinding` records carry a unique `(rule, source_index, wazuh_doc_id)` key so re-runs over overlapping windows never materialise duplicate Alerts. A live-firing record per `(rule, entity_value)` ensures new Findings for the same key link into the open incident rather than spawning a new one.
- **Flood cap** — at most 50 Findings are materialised per run; if more documents match, an overflow note is added to the incident so operators are aware of the capped set.
- **Streaming suppression** — materialised search-alerts are excluded from the streaming correlation evaluator so the two engines never produce competing incidents from the same documents.
- **System rules and per-org fan-out** — system Scheduled Search Rules (no org) run for every tenant with each query scoped to that org's Wazuh agents. Tenants are always fully isolated; no cross-tenant correlation can occur.
- **Per-org failure isolation** — if one tenant's OpenSearch query fails during a system rule fan-out, the error is recorded and the remaining tenants continue running.
- **Per-org mutes** — admins can mute any system Scheduled Search Rule for a specific tenant, mirroring the Correlation Rule mute mechanism.
- **LLM-assisted author drawer** — a two-pass drafting flow: first the assistant fetches a menu of real Wazuh rule IDs and titles (from a live `rule.id` aggregation over OpenSearch) so analysts pick the relevant rules; then it expands those selections into a full leg-and-condition draft grounded in the actual Wazuh data — not synthetic guesses.
- **Mapping-aware sanitizer** — the LLM draft is validated against the live index mapping before it reaches the builder; invalid fields and operator/type mismatches are dropped with a warning rather than silently accepted.
- **`scheduled_search` source kind** — incidents raised by this engine are tagged with a distinct `source_kind` so they are filterable in the inbox and clearly distinguishable from push-based incidents.
- **IOC extraction and triage** — incidents created from Scheduled Search Rules pass through the same IOC enrichment and LLM triage pipeline as any other incident.

---

## Rule Tests

Detection-as-code testing for Scheduled Search Rules — pin a rule's behaviour with synthetic fixtures so a future edit can't silently break it.

- **Sample-document fixtures** — a Rule Test bundles a set of synthetic **Sample Documents** (partial raw Wazuh JSON) with a whole-rule fire / no-fire **Expectation**. Each run produces a pass/fail **Test Result**.
- **Real engine, not a simulator** — every run spins up an ephemeral, non-glob-matching OpenSearch index, clones the live alerts-index mapping onto it, pushes the sample documents straight in (bypassing Wazuh), and runs the *actual* compiler, join, and Diversity/Novelty Constraint logic against them — then drops the index. What the test exercises is exactly what production runs.
- **Era-spanning sample timestamps** — Sample Documents support relative `@timestamp` offsets (e.g. `now-40d`, `now-5m`) resolved when the ephemeral index is populated, so a Novelty Constraint test can place a baseline doc and a detection doc in distinct time eras and stay valid whenever it runs. Literal timestamps still work; pure count/diversity tests are unaffected.
- **Zero side effects** — the evaluator has a decide/materialise split; the test path is decide-only, so a run creates no Incidents, Alerts, Findings, or firing records. The detection window is anchored to the latest sample timestamp, keeping tests time-stable.
- **Tests drawer** — author and run tests from a dedicated drawer off each rule's list row, separate from the definition editor. The list row shows a health badge (e.g. "Tests 3/4") and a **Run all** action to re-check every test at once.
- **LLM sample generator** — generate grounded true-positive / true-negative Sample Documents for a rule with the LLM, so analysts get a realistic starting fixture set instead of hand-writing raw Wazuh JSON.
