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
_Avoid_: Correlation Rule (reserved for the in-app, push, multi-leg engine over ingested Alerts), Saved Search (a Scheduled Search Rule is evaluated and can raise findings, not just stored). Note: **Hunt** is now a distinct defined concept (the interactive LLM threat-hunting module) — a Scheduled Search Rule is its opposite (non-interactive, scheduled, *pull*), so keep the two apart.

**Finding**:
A single raw Wazuh document that a **Scheduled Search Rule**'s query *or a **Hunt**'s lens* matched. When a Scheduled Search Rule triggers, each Finding is **materialised** as an in-app **Alert** (the matches are ingested on trigger — only the matches, never the whole index), and the run's Findings together produce one **Incident**. A **Hunt** reuses the identical substrate and materialise bridge: its matched docs are Findings, grouped by affected org, and each group becomes a **propose-and-confirm** Incident the staff member confirms (materialised on confirm). A behavioral Hunt's *aggregate* insight (e.g. "host X: 400 failed logins then a success") is the model's narrative *over* a set of Findings — the underlying docs remain the materialisable evidence; it is not a separate concept. Almost always there is no pre-existing app Alert for a Finding, since the platform does not ingest the full Wazuh stream.
_Avoid_: Hit, Match (use "match" only as the verb for the query selecting a document).

A Scheduled Search Rule is a **System Rule** (org = null, baseline applied to every tenant, per-org **Mute**) or an **Org Rule** (org set) — the same tiers as a Correlation Rule. **Tenant-isolation invariant:** every query is scoped to one organisation's Wazuh agents (`agent.id` ∈ the org's `wazuh_group` members), and a rule's **Window** / **Correlation Key** join *never* crosses tenants — even `correlation_key = none` correlates only within a single org's agent scope. A System Search Rule achieves this by fanning out per org (excluding mutes) at run time.

**Diversity Constraint**:
An additional satisfaction requirement on a **Leg** of a **Scheduled Search Rule**: the leg's matching documents, grouped by the rule's **Correlation Key**, must span at least M *distinct values* of a chosen field (e.g. ≥ 2 distinct `country` for the same `user.name`). It is a property of a Leg, evaluated *alongside* the leg's document-count threshold — both must hold for the leg to be satisfied for a key. It expresses "spread across N different X," which the plain count threshold (which only counts *how many* documents matched) cannot. The motivating case is multiple successful logins for one user originating from two or more different countries within the **Window**. See [ADR-0009](docs/adr/0009-leg-level-diversity-constraint.md).
_Avoid_: Condition (reserved for the field-level predicate *filter* inside a leg — a Diversity Constraint is an aggregation threshold, not a filter), Impossible Travel (that connotes a geo-distance ÷ time physics check, a deliberately deferred future axis — a Diversity Constraint is pure set-cardinality with no geography or distance).

**Materialise**:
To create an in-app **Alert** from a **Finding** at trigger time. The bridge that lets a Scheduled Search Rule reuse the existing Incident / IOC / triage pipeline, which all assume real Alert rows. In v1 a materialised search-alert is **born-linked + suppressed**: created with `source_kind = scheduled_search`, already linked to its rule's Incident. Suppression is two-part — it does not *trigger* streaming evaluation, **and** it is excluded from other rules' streaming window scans — so it participates only in its own Search Rule incident and never seeds streaming cross-source correlation. Its Incident also carries `source_kind = scheduled_search`, keeping it outside the streaming `Supersede` logic. (v2 may relax this — see issue #399.)

### Detection testing

**Rule Test**:
A named, saved test attached to one **Scheduled Search Rule** — the detection-as-code "unit test" for that rule. It bundles a set of **Sample Documents** and one **Expectation**, and is run on demand to check whether the rule still behaves as its author intended. A rule has zero or more Rule Tests; running one produces a **Test Result**. It tests the *whole rule's* external behaviour (does it fire?), never a **Leg** or **Condition** in isolation.
_Avoid_: "logging rule" (a Rule Test is not a kind of detection rule), Fixture (too generic), Correlation Rule / Scheduled Search Rule (a Rule Test is *about* a rule, it is not itself a rule that detects).

**Sample Document**:
One synthetic raw Wazuh document supplied to a **Rule Test** as input the rule under test is evaluated against. Shaped like a real Wazuh OpenSearch document so the same compiled query/match logic applies. Deliberately distinct from a **Finding** (a *real* matched document from production data) and from an **Alert** (a Sample Document is never materialised or ingested).
_Avoid_: Finding, Alert, Sample Log (prefer "Document" to match the Wazuh document schema the rule matches over).

**Expectation**:
What a **Rule Test** asserts the rule should do with its **Sample Documents** — at minimum *should-fire* vs *should-not-fire* (true-positive / true-negative). Expressed at whole-rule granularity.
_Avoid_: Assertion at leg/condition level (out of scope; the Expectation is about the rule firing, not internal leg satisfaction).

**Test Result**:
The outcome of running a **Rule Test**: pass/fail against its **Expectation**, plus diagnostics explaining *why* (e.g. which **Leg** fell short, which key satisfied/missed, diversity shortfall). The diagnostics are explanatory only — they are not authored **Expectation**s.
_Avoid_: Finding, Firing (a Test Result records a test run, not a production detection event).

### LLM-assisted detection

**Residual**:
Alerts that no static rule promoted or linked — still `new`/unlinked, aged past a settle delay, within a lookback window. The input the LLM safety-net reasons over.

**Detection Suggestion**:
A proposed grouping of Residual alerts the LLM flags as suspicious, carrying a rationale and confidence, surfaced in the inbox for an analyst to accept (→ Incident) or dismiss. In v1 the LLM never auto-creates incidents. See [ADR-0004](docs/adr/0004-llm-residual-safety-net-suggestion-only.md).
_Avoid_: Alert (a Suggestion is about a *group* of alerts and is analyst-facing, not a source signal).

**Rule Draft**:
An unsaved, proposed **Correlation Rule** the LLM assembles from a natural-language detection description (e.g. "alert when a new user is created then logs in within 24h"). Presented pre-filled in the rule builder for a human to review, edit, and save; it is never persisted until saved as a real Correlation Rule, and the LLM never activates a rule itself. Produced by a stateless, multi-turn drafting conversation grounded in the scope's recent alerts; the drafter may also **search the internet** for threat intelligence to inform what to detect (the rule-catalog/field retrieval itself stays the existing two-pass flow — converting it to tools is deferred, issue #402). See [ADR-0005](docs/adr/0005-rule-author-assistant-ephemeral-stateless.md) and [ADR-0011](docs/adr/0011-assistant-agentic-tool-calling-loop.md).
_Avoid_: Detection Suggestion (that is the LLM acting on a *group of past alerts* to propose an Incident; a Rule Draft is the LLM acting on *a human's words* to propose a future-matching Rule). Avoid Suggestion (overloaded with Detection Suggestion).

**Incident Assistant**:
A staff-only, conversational LLM interface embedded in the incident detail view. Answers questions about a specific incident using live server-side grounding (the incident's own fields, linked alerts, IOCs, tasks, available task templates) and can **reach beyond that seed via tools** — looking up related incidents, alerts, and assets in the app, and searching the internet for threat intelligence — to inform its answer. The conversation is ephemeral (client state, not persisted) and the seed grounding is recomputed server-side every turn. Actions split by risk: the assistant **auto-executes a bounded set of internal, reversible, non-lifecycle actions** (e.g. add an internal comment, self-assign, tag, link a known asset, **record findings on a manual task**), each audited; everything externally-visible or lifecycle/severity/disclosure-affecting (state transition, severity/TLP/PAP/subject/assignee change, task-template application, contact message, exception, close) remains a **proposal the analyst confirms**. It can also **work the incident's manual tasks** — researching each, then recording its findings as a task-scoped internal comment — but it **never executes `automated` or `wazuh_response` tasks** (those touch live infrastructure) and **never closes a task itself**: completing a task stays the SOC member's choice. See [ADR-0011](docs/adr/0011-assistant-agentic-tool-calling-loop.md), [ADR-0012](docs/adr/0012-incident-assistant-relaxed-action-authority.md) (which supersedes [ADR-0008](docs/adr/0008-incident-assistant-propose-and-confirm.md)), and [ADR-0013](docs/adr/0013-incident-assistant-works-manual-tasks.md).
_Avoid_: conflating with Detection Suggestion (which is about grouping alerts pre-incident) or Rule Draft (which is about authoring Correlation Rules). _Avoid_: assuming the assistant can autonomously take *any* action — autonomy is bounded to the internal/reversible/non-lifecycle set; higher-risk actions still require human confirmation.

**Hunt**:
A staff-initiated, LLM-assisted threat-hunting investigation — a *new module* distinct from the **Incident Assistant**. Where the Incident Assistant is incident-*bound* (it lives inside one incident and is seeded by it), a Hunt is incident-*producing*: it starts from no incident, seeded by a staff member's free-text question or a link to an external malware/threat report, then ranges over Wazuh telemetry (via the existing org-scoped `OpenSearchClient`/`WazuhClient`, **not** an external MCP server in v1) to find whether the IOCs/patterns it identifies appear in the customer fleet. It reuses the Incident Assistant's plumbing — the shared agentic orchestrator, providers, native web search, and SSE/async streaming ([ADR-0011](docs/adr/0011-assistant-agentic-tool-calling-loop.md), [ADR-0014](docs/adr/0014-incident-assistant-sse-streaming.md)) — but is its own concept with its own grounding, surface, and output authority. See [ADR-0015](docs/adr/0015-threat-hunting-incident-producing-module.md) (the module: incident-producing, persisted, propose-and-confirm, own-clients-not-MCP) and [ADR-0016](docs/adr/0016-hunt-runs-as-background-job-streamed-over-sse.md) (each turn runs as a Celery background job streamed over reconnectable SSE). Unlike the Incident Assistant's *ephemeral* conversation, a Hunt is a **first-class persisted, resumable, auditable entity** (seed, owner, org scope, transcript/tool-trace, findings, spawned-incident links): a staff member can continue a hunt later, review earlier hunts, and the record is the audit trail for cross-tenant access. Its durable transcript *is* its grounding (there is no incident seed to recompute). "Resumable" means a human adds more turns — **not** an automatic scheduled re-run (that is a **Scheduled Search Rule**'s job). When a Hunt finds something, it does not auto-create incidents: it surfaces findings grouped by affected org and offers a **propose-and-confirm** Incident per org ([ADR-0004](docs/adr/0004-llm-residual-safety-net-suggestion-only.md)'s human-in-the-loop principle holds), **materialising** the matched raw Wazuh docs as Alerts on confirm (reusing the Scheduled Search Rule bridge). **v1 is staff-only and cross-org** (the SOC hunts threats across all tenants, a sanctioned staff right); a later v2 may expose constrained single-org hunting to org members. When a Hunt finds something needing human investigation it does **not** silently spawn an incident — see _Flagged ambiguities_ for the open output-authority question (Detection Suggestion vs proposed Incident vs auto-create).
_Avoid_: Scheduled Search Rule (non-interactive, scheduled *pull* detection — a Hunt is interactive and human-initiated), Detection Suggestion (that is the LLM grouping *existing* unlinked alerts; a Hunt actively *seeks* threats from a seed and reaches into raw Wazuh data), Incident Assistant (incident-bound, not incident-producing).

**Shared Infrastructure event** (a.k.a. _agentless event_):
A Wazuh document **not linked to any tenant's agent** — it is logged against the Wazuh **manager** (`agent.id = "000"`) rather than an agent in some org's `wazuh_group`. In this deployment these are the perimeter sources shared across *all* tenants: a single **firewall** and a single **reverse proxy** that forward via the manager (syslog), so the document carries **no per-org attribution** at all. This is the deliberate exception to the **Tenant-isolation invariant** (which attributes an event to an org *only* by `agent.id` ∈ that org's `wazuh_group`): a Shared Infrastructure event belongs to no one tenant and to all of them at once. The Scheduled-Search world already names this *agentless/infrastructure mode* (`include_agentless` ⇒ the `agent.id` filter is dropped); threat hunting needs the same reach because perimeter telemetry is essential evidence.

A Hunt attributes such events to the **Infrastructure organisation** (below) and selects them with the positive filter `agent.id = "000"` (never by *dropping* the agent filter — that would glob every tenant's data into one un-attributed query). See [ADR-0017](docs/adr/0017-shared-infrastructure-pseudo-org-for-agentless-hunting.md).
_Avoid_: "an org's firewall" (the firewall/proxy are shared, owned by no tenant), Agent (a Shared Infrastructure event is precisely the *absence* of a per-host agent).

**Infrastructure organisation**:
A dedicated, **non-tenant** `Organization` row (`is_infrastructure = True`) that is the home for **Shared Infrastructure events**. It owns no customer, has no `wazuh_group` members, and is **excluded from every "real tenant" code path** — System Search Rule fan-out, fleet vulnerability scans, per-org incident tasks, billing/dashboards/tenant counts — via a tenants-only queryset. It is visited **only** by **Hunt** scope resolution: an *all-orgs* Hunt includes it automatically, and it is also selectable on its own in the staff hunt-scope picker. Its query scope is special-cased to `agent_ids = ["000"]` rather than resolved through `get_agents(wazuh_group)`. Because it is a real `Organization`, infra **Findings** ride the normal **propose-and-confirm** path and **materialise** into an **Incident** *in the Infrastructure organisation* — keeping a real, agent-bound tenant's incidents free of mis-attributed perimeter events. See [ADR-0017](docs/adr/0017-shared-infrastructure-pseudo-org-for-agentless-hunting.md).
_Avoid_: Tenant / customer org (it represents shared perimeter infrastructure, not a paying tenant — never invite users to it, bill it, or fan System Rules out to it).

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
