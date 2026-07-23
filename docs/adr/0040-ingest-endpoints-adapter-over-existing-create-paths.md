# Webhook Ingest Endpoints: an adapter over existing create paths, not a new pipeline

## Status

accepted

## Context

Remote systems (SIEMs, scanners, ticketing, CMDBs) want to push records into the platform
over **webhooks** — but a webhook's body shape is dictated by the *sender*, so the fixed
API endpoints can't consume it directly. We need a configurable intake — an **Ingest
Endpoint** (`CONTEXT.md` → *Webhook ingest*) — that accepts arbitrary sender JSON and turns
it into an **Incident**, **Alert**, or **Asset** in one target **Organization**. The
question is *how the mapped record enters the domain*: through a purpose-built webhook
ingestion pipeline, or through the internal create paths the platform already has.

## Decision

An Ingest Endpoint is a **translation/adapter front-end only**. Its job ends at producing
the canonical payload the platform's *existing* internal create already consumes, then
calling that same code:

- **Alert** → the existing alert-ingest service (`AlertListIngestView` / V2), so a
  webhook alert is wrapped in the **ECS entity envelope** and run through **correlation**
  like every other alert. It is **never** a bare row — preserving the ADR-0001 ingestion
  invariant for free. An Alert mapping that resolves no recognised ECS entity therefore
  **fails** (the V2 ingest requires a valid entity envelope).
- **Incident** → `IncidentCreateSerializer` + `next_display_id()`, carrying a new
  `source_kind = "webhook"` for queryable provenance (mirroring how partner intake got its
  own `source_kind = "partner"`, ADR-0032).
- **Asset** → the asset create/update path.

Write semantics are **per target type**, not uniform: Incident/Alert are *event-like*
(every element **creates a new** record; the per-element idempotency key only suppresses
retry/replay double-creates), whereas **Asset** is *inventory-like* — a re-pushing feed
**upserts** on a designated identity field (default `name`, matched within the target org),
with a Wazuh `agent_name` left NULL so webhook assets never collide with agent-discovered
host assets under `unique_host_asset_per_org`.

## Considered options

- **A dedicated webhook ingestion pipeline** (parallel to the alert/incident paths).
  Rejected: it would duplicate — and inevitably drift from — correlation wiring, display-id
  allocation, serializer validation, and side effects. Worse, a webhook alert built outside
  the ECS-envelope path would be a second-class alert that violates ADR-0001, exactly the
  foreign-object outcome we wanted to avoid.
- **Uniform "call the create path" for all three types.** Rejected: assets are inventory,
  not events. Blind-create fails on every re-push (`unique_host_asset_per_org`
  IntegrityError → dead-letter), so the asset target must resolve an identity and
  upsert-or-create. The adapter is uniform in *reusing existing code*, not in *the verb*.

## Consequences

- The mapping engine's output contract is "the payload the internal create already
  accepts" — the Ingest Endpoint owns *mapping + caching + auth*, not domain creation
  logic. New target types are added by pointing at their existing create path plus a
  mapping section.
- Webhook alerts inherit correlation/Supersede automatically; there is no separate
  code path to keep in sync.
- Assets rely on a **soft** identity (`name`, no DB uniqueness constraint), so concurrent
  double-posts can race two rows — the upsert must guard with `select_for_update` /
  get-or-create. Promoting `name` to a real per-org constraint is a future option.
