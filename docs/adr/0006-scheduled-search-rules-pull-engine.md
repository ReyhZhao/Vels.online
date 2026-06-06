# Scheduled Search Rules are a pull-based sibling engine that materialises matches on trigger

The original correlation engine ([ADR-0001](0001-ecs-entity-envelope-at-ingestion.md)..[0005](0005-rule-author-assistant-ephemeral-stateless.md)) is **push**: it reacts to **Alert**s ingested into the platform. That cannot detect patterns over the *full* Wazuh stream without ingesting all of it — wasteful, and better left to OpenSearch. So we add a second, distinct detection paradigm — the **Scheduled Search Rule** — that, on a schedule, pushes its pattern-match *down into* the Wazuh OpenSearch backend, and only when a pattern is found does it **materialise** the matched documents (**Findings**) as in-app Alerts and produce one Incident. It reuses the rule-authoring UX (legs, conditions, LLM-assisted drafting) but is a separate model, separate ledger (`SearchFiring`), and separate execution path, all in the `correlations` app.

## Considered Options

- **Pull-based sibling that materialises matches (chosen)** — scheduled query → materialise only the matches → Incident. Keeps the full Wazuh stream in OpenSearch where it belongs; reuses the existing Incident / IOC / triage pipeline because Findings become real Alerts.
- **Ingest the whole Wazuh stream and let the existing push engine handle it** — conceptually uniform, but copies a massive event stream into the platform for no benefit; rejected as the explicit non-goal.
- **A new `mode` flag on `CorrelationRule`** — overloads a glossary term that deliberately means "in-app, push, multi-leg over the entity envelope." The field catalog (dynamic Wazuh namespace vs app-normalised), dedup mechanism (doc-id idempotency vs live-firing-per-entity), and execution (scheduled vs reactive) all differ, so one model would mean two contradictory things.

## Consequences

- **Two-part suppression boundary (v1).** A materialised search-alert is *born-linked + suppressed*: it carries `source_kind = scheduled_search`, is created already linked to its rule's Incident, does **not** trigger streaming evaluation, **and** is excluded from other rules' streaming window scans (`evaluator._get_window_alerts`). Its Incident also carries `source_kind = scheduled_search`, keeping it outside streaming `Supersede`. The two engines stay genuinely separate; letting search-alerts flow into streaming cross-source correlation is deferred (issue #399).
- **Dedup is doc-id idempotency, not a timestamp watermark.** A `SearchFinding` row keyed unique on `(rule, source_index, wazuh_doc_id)` makes overlapping-window re-matches no-ops and survives late-arriving docs; live-firing (`SearchFiring`, one open incident per `(rule, key)`) dedups incidents. A watermark is at most a cost optimisation.
- **Co-occurrence, not ordering.** Multi-leg match means "all legs present for the same key within the window," compiled via per-leg `terms` aggregations on the correlation key plus a Python join — matching the streaming engine's semantics. Strict sequence ordering is deferred.
- **Tenant isolation is the hard boundary.** Every query is scoped to one org's Wazuh agents; correlation never crosses tenants, even for `correlation_key = none`. System Search Rules fan out per org (excluding mutes) at run time, accepting the N-orgs × M-legs cost.
- **Bounded blast radius.** A run materialises at most `max_findings_per_run` (default 50) Findings, recording an overflow note for the rest.
- Per-rule scheduling uses one `django_celery_beat` `PeriodicTask` per rule (run-state visibility + ad-hoc "Run now"), not a single global sweep.
