# Vels Online — Security Operations Context

The domain language for turning multi-source security signals into actionable
investigations: alerts arrive, get correlated, and become incidents that analysts work.

## Language

### Alerts & detection

**Alert**:
A single security signal from one source (Wazuh event, vulnerability, agent finding, inbound email, API). Has a `source_kind`, free-form `source_ref`, severity, and state.
_Avoid_: Event (reserve for raw Wazuh events upstream), Finding.

**Correlation Rule**:
A user-defined rule that promotes a combination of alerts to an Incident when its legs are all satisfied for the same correlation key within a time window.
_Avoid_: Detection, Pattern, Filter (too vague — a rule is specifically multi-leg + key + window).

**Leg**:
One sub-condition of a Correlation Rule, matching a distinct *class* of alert by its fields (e.g. `title CONTAINS "port scan"`). A rule has one or more legs.
_Avoid_: Clause, Condition (reserve "condition" for the field-level predicate inside a leg).

**Entity**:
A normalised, queryable value carried on an Alert in its **entity envelope**, named per Elastic Common Schema (`host.name`, `source.ip`, `user.name`, `file.hash.sha256`, `process.name`). Sources populate the envelope (required on the ingestion API; canonicalised on ingest); the platform does not extract entities itself. Legs across different `source_kind`s join on shared Entities. See [ADR-0001](docs/adr/0001-ecs-entity-envelope-at-ingestion.md).
_Avoid_: Field, Attribute (those are raw `source_ref` keys, pre-normalisation).

**Correlation Key**:
The Entity type a Correlation Rule binds its legs on. Per-rule choice (`agent`, `source_ip`, `username`, …, or `none` = correlate across all alerts org-wide). `none` rules are typically single-leg.
_Avoid_: Group key, Join key.

**Window**:
The rolling time span within which all of a rule's legs must be satisfied to trigger.

**Firing**:
A single triggering of a Correlation Rule for one Correlation Key value, recorded in a ledger as `(rule, entity_value, incident, fired_at)`. At most one *live* (open-incident) Firing exists per `(rule, entity_value)`; while it is live, further matching alerts link into its incident rather than spawning a new one. A new Firing is only allowed after the prior incident closes.
_Avoid_: Match, Hit, Trigger (use "trigger" only as the verb).

**System Rule**:
A Correlation Rule authored centrally by the Vels SOC (`organization = null`) and applied to every tenant as baseline detection. Tenants cannot edit it but can **mute** it for themselves. See [ADR-0003](docs/adr/0003-system-baseline-plus-per-org-overlay-rules.md).

**Org Rule**:
A Correlation Rule a tenant authors for its own organisation (`organization` set).

**Mute**:
A per-org disablement of a System Rule — the rule stops evaluating for that tenant only, without being deleted globally.
_Avoid_: Disable, Suppress (suppress could be confused with Firing dedup).

### Scheduled search

**Scheduled Search Rule**:
A user-defined rule that, on a schedule, pushes its pattern-match down into the Wazuh **OpenSearch** backend to detect a pattern of raw Wazuh alerts *without* ingesting all of them into the platform. Authored with the same manual + LLM-assisted builder as a **Correlation Rule**, but it is a distinct concept: it evaluates by *pull* (a periodic query) rather than by *push* (reacting to an ingested **Alert**), it matches over the raw Wazuh document schema rather than the normalised **entity envelope**, and it has no in-app **Alert** rows until it triggers. See [ADR-0006](docs/adr/0006-scheduled-search-rules-pull-engine.md) and [ADR-0007](docs/adr/0007-search-rule-dynamic-field-catalog.md).
_Avoid_: Correlation Rule (reserved for the in-app, push, multi-leg engine over ingested Alerts), Hunt (connotes interactive/exploratory threat hunting), Saved Search (a Scheduled Search Rule is evaluated and can raise findings, not just stored).

**Finding**:
A single raw Wazuh document that a Scheduled Search Rule's query matched on a given run. When a rule triggers, each Finding is **materialised** as an in-app **Alert** (the matches are ingested on trigger — only the matches, never the whole index), and the run's Findings together produce one **Incident**. Almost always there is no pre-existing app Alert for a Finding, since the platform does not ingest the full Wazuh stream.
_Avoid_: Hit, Match (use "match" only as the verb for the query selecting a document).

A Scheduled Search Rule is a **System Rule** (org = null, baseline applied to every tenant, per-org **Mute**) or an **Org Rule** (org set) — the same tiers as a Correlation Rule. **Tenant-isolation invariant:** every query is scoped to one organisation's Wazuh agents (`agent.id` ∈ the org's `wazuh_group` members), and a rule's **Window** / **Correlation Key** join *never* crosses tenants — even `correlation_key = none` correlates only within a single org's agent scope. A System Search Rule achieves this by fanning out per org (excluding mutes) at run time.

**Materialise**:
To create an in-app **Alert** from a **Finding** at trigger time. The bridge that lets a Scheduled Search Rule reuse the existing Incident / IOC / triage pipeline, which all assume real Alert rows. In v1 a materialised search-alert is **born-linked + suppressed**: created with `source_kind = scheduled_search`, already linked to its rule's Incident. Suppression is two-part — it does not *trigger* streaming evaluation, **and** it is excluded from other rules' streaming window scans — so it participates only in its own Search Rule incident and never seeds streaming cross-source correlation. Its Incident also carries `source_kind = scheduled_search`, keeping it outside the streaming `Supersede` logic. (v2 may relax this — see issue #399.)

### LLM-assisted detection

**Residual**:
Alerts that no static rule promoted or linked — still `new`/unlinked, aged past a settle delay, within a lookback window. The input the LLM safety-net reasons over.

**Detection Suggestion**:
A proposed grouping of Residual alerts the LLM flags as suspicious, carrying a rationale and confidence, surfaced in the inbox for an analyst to accept (→ Incident) or dismiss. In v1 the LLM never auto-creates incidents. See [ADR-0004](docs/adr/0004-llm-residual-safety-net-suggestion-only.md).
_Avoid_: Alert (a Suggestion is about a *group* of alerts and is analyst-facing, not a source signal).

**Rule Draft**:
An unsaved, proposed **Correlation Rule** the LLM assembles from a natural-language detection description (e.g. "alert when a new user is created then logs in within 24h"). Presented pre-filled in the rule builder for a human to review, edit, and save; it is never persisted until saved as a real Correlation Rule, and the LLM never activates a rule itself. Produced by a stateless, multi-turn drafting conversation grounded in the scope's recent alerts. See [ADR-0005](docs/adr/0005-rule-author-assistant-ephemeral-stateless.md).
_Avoid_: Detection Suggestion (that is the LLM acting on a *group of past alerts* to propose an Incident; a Rule Draft is the LLM acting on *a human's words* to propose a future-matching Rule). Avoid Suggestion (overloaded with Detection Suggestion).

**Incident Assistant**:
A staff-only, conversational LLM interface embedded in the incident detail view. Answers questions about a specific incident using live server-side grounding (fields, linked alerts, IOCs, tasks, available task templates) and proposes a bounded set of one-click actions (field update, state transition, or task-template application) for human confirmation. The conversation is ephemeral (client state, not persisted), grounding is recomputed server-side every turn, and the assistant never mutates incident data on its own — every proposed change is confirmed by the analyst and executed through the existing mutation endpoints. See [ADR-0008](docs/adr/0008-incident-assistant-propose-and-confirm.md).
_Avoid_: autonomous writes (the assistant always proposes; a human confirms). _Avoid_: conflating with Detection Suggestion (which is about grouping alerts pre-incident) or Rule Draft (which is about authoring Correlation Rules).

## Relationships

- A **Correlation Rule** is either a **System Rule** (org = null) or an **Org Rule**; it has one or more **Legs** and exactly one **Correlation Key**.
- A tenant evaluates: **System Rules** it has not **Muted**, plus its own **Org Rules**.
- A **Correlation Rule** that triggers produces one **Incident** and links the contributing **Alerts** to it.
- An **Alert** belongs to at most one **Incident** (existing `Alert.incident` FK).

**Supersede**:
What a triggering Correlation Rule does to a simpler incident that already owns one of its contributing alerts: relink the alerts to the chain incident, then mark the simpler incident `duplicate_of` it and close it. Reversible; history preserved on the closed incident. See [ADR-0002](docs/adr/0002-correlation-rules-supersede-via-duplicate-of.md).
_Avoid_: Merge (reserve for the deferred A-deep record-level migration).

## Flagged ambiguities

- "Combination of alerts" was ambiguous between a single-alert classifier (conditions over one alert) and a multi-leg correlation across heterogeneous alerts. **Resolved:** a Correlation Rule is multi-leg correlation; a single-leg rule is the degenerate case that subsumes the old severity auto-promote.
- The hardcoded `route_alert` steps (severity auto-promote, asset threshold) overlap with Correlation Rules. **Resolved (v1):** both run side by side — fast-path stays synchronous, Correlation Rules run async and **Supersede** any simpler incident they overlap. Eventually the hardcoded steps may be reframed as seed rules (deferred).
- A **Scheduled Search Rule** reuses the **Leg** / **Correlation Key** / **Window** vocabulary, but its match semantics are **co-occurrence within the window** ("all legs present for the same key"), *not* strict ordering ("leg A *then* leg B"). **Resolved (v1):** co-occurrence only, matching the streaming engine. Strict sequence/ordering is a recognised future axis (may matter once rules run in production for a while) — deferred.
