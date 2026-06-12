# A Hunt turn runs as a background job streamed over reconnectable SSE

[ADR-0014](0014-incident-assistant-sse-streaming.md) runs the Incident Assistant's agentic loop **in-request** on a worker thread and **cancels it on client disconnect** (`GeneratorExit` → `cancel_event`), bounded by a short `ASSISTANT_LOOP_DEADLINE_S` sized to fit under proxy timeouts. That is correct for a quick, incident-bound Q&A. A **Hunt** ([ADR-0015](0015-threat-hunting-incident-producing-module.md)) breaks all three assumptions: it is persisted and **resumable**, runs **minutes** (cross-org fan-out + behavioral lenses + a report fetch), and must **survive a dropped socket** rather than die with it. So a Hunt turn does not run in the request.

## Decision

- **Each hunt turn runs as a Celery background job** (we already operate Celery: `celery_tasks/`, `security/tasks.py`). The worker runs the same ADR-0011 orchestrator and **writes ADR-0014's event vocabulary** (`phase`, `tool`, `action`, `result`, `error`, `done`) onto the persisted **Hunt** record's event log.
- **The SSE endpoint becomes a tail/replay of that persisted event log**, not the execution itself. A reconnect after a dropped socket catches up from the last seen event; the worker keeps running regardless of whether anyone is listening. Execution lifetime is **decoupled** from connection lifetime — which is what makes "continue where you left off" actually work.
- **Keep ADR-0014's event taxonomy unchanged**; only the *source* of events moves (from an in-thread queue to the persisted log) and the *cancel* semantics change (a hunt is cancelled explicitly by the owner, not by a transport disconnect).
- **Hunt caps are relaxed** relative to the Incident Assistant, since a background worker removes proxy-timeout pressure: more iterations per turn, a longer per-tool timeout, and a wall-clock deadline measured in minutes, plus a per-lens fan-out cap (max orgs/agents scanned per query, paginated).

## Considered Options

- **Reuse ADR-0014 in-request SSE verbatim** — cheapest (zero new infra), but cancel-on-disconnect kills a multi-minute cross-org sweep when a socket drops, "resume" degrades to "start a fresh turn," and the short deadline can't fit the work. It quietly breaks the persistence/resume contract of ADR-0015.
- **Background job + reconnectable SSE (chosen)** — more work, but the only model that delivers resume, disconnect-survival, and a minutes-long cross-org runtime while preserving ADR-0014's event contract.

## Consequences

- A Hunt needs a persisted, append-only event log (the streaming source and part of the audit trail), and an explicit cancel path on the Hunt record.
- Two streaming sources now coexist: the Incident Assistant's in-thread queue (ADR-0014) and the Hunt's persisted log. The wire event vocabulary is shared, so the frontend SSE consumer can be largely reused.
- Background execution lifts the deadline ceiling but shifts cost to worker capacity; cross-org fan-out must be bounded/paginated so one hunt cannot saturate the workers.
