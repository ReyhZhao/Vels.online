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

### LLM-assisted detection

**Residual**:
Alerts that no static rule promoted or linked — still `new`/unlinked, aged past a settle delay, within a lookback window. The input the LLM safety-net reasons over.

**Detection Suggestion**:
A proposed grouping of Residual alerts the LLM flags as suspicious, carrying a rationale and confidence, surfaced in the inbox for an analyst to accept (→ Incident) or dismiss. In v1 the LLM never auto-creates incidents. See [ADR-0004](docs/adr/0004-llm-residual-safety-net-suggestion-only.md).
_Avoid_: Alert (a Suggestion is about a *group* of alerts and is analyst-facing, not a source signal).

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
