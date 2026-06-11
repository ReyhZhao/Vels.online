# Incident Assistant moves to SSE streaming (v2)

Follow-up to [ADR-0011](0011-assistant-agentic-tool-calling-loop.md) (agentic tool-calling loop v1). Scope is the **Incident Assistant** only; the Rule Draft assistant stays on the blocking path for now.

## Decision

**ASGI flip.** The whole backend moves to ASGI (`config/asgi.py`, `ASGI_APPLICATION`), served by **gunicorn with the uvicorn worker class**. All existing sync DRF views continue to run unchanged in Django's threadpool. Only the one streaming endpoint is async. Chosen over a gevent worker class and over isolating the endpoint in a separate ASGI process — simplest topology, leaves the stack streaming-ready for the deferred Rule Draft migration.

**Transport replaced, not aliased.** The streaming endpoint replaces the transport at the existing URL (`POST /api/incidents/<display_id>/assistant/` now returns `text/event-stream`). No parallel `/stream/` path. Excluded from the drf-spectacular schema.

**Tool-step granularity, not token streaming.** Both providers (Ollama, Gemini) make non-streaming SDK calls and the synthesis is a structured call; token streaming would require new provider methods and fragile partial-JSON handling for no proportional gain. The event sequence is: `phase` (research | synthesis), `tool` (one per tool call/result), `action` (one per auto-executed write the moment it commits), `result` (terminal structured envelope), `error`, `done`. `done` is always emitted last from a `finally` block.

**Sync orchestrator stays synchronous.** `run_research_phase` gains an optional `on_event` callback (fired at each tool call/result and phase boundary) and a cooperative `cancel_event` (`threading.Event`) checked at the top of each iteration. The return value and existing behaviour are preserved when neither is supplied — existing tests and the Rule Draft path are unaffected.

**Sync→async bridge.** The streaming view runs the sync orchestrator on a worker thread via `sync_to_async(thread_sensitive=False)` so concurrent streams get their own thread and DB connection and never serialise. Events are pushed into a thread-safe queue that the async SSE generator drains and frames. On client disconnect (`GeneratorExit`), the view sets the `cancel_event`.

**Error/terminal contract.** Pre-stream failures (auth, `is_staff`, incident not found, provider unconfigured, missing `messages`) return normal HTTP status codes — no stream opened. Once the stream is open (200 + `text/event-stream`), all outcomes are in-stream events (`result` on success, `error` on failure), always followed by `done`.

**nginx buffering.** The streaming response sets `X-Accel-Buffering: no` so nginx does not buffer chunks before forwarding to the browser.

## Considered Options

- **Gevent worker** — would make all views cooperative-concurrent without the ASGI complexity, but cannot host true async views and the gevent monkey-patch is intrusive. Ruled out.
- **Separate ASGI process for the streaming endpoint** — isolates the async surface but adds routing complexity and a second process to operate. Ruled out.
- **Token streaming** — requires new provider SDK paths, fragile partial-JSON parsing for structured synthesis output, and provides no proportional analyst value over tool-step events. Deferred indefinitely.
- **Content-negotiated JSON fallback** — a buffering fallback would reintroduce the dead-spinner/timeout problems the streaming transport exists to remove. Ruled out.

## Consequences

- A long streaming response on a uvicorn worker never triggers gunicorn's sync `--timeout` kill; the loop's own internal deadline caps (`ASSISTANT_LOOP_DEADLINE_S`) are still respected but the external kill pressure relaxes.
- Postgres connection count: `CONN_MAX_AGE=600` × threadpool threads can multiply open connections under load. Operators should smoke-test after the ASGI flip.
- The Rule Draft assistant path is unaffected and is left streaming-ready for a follow-up migration.
- `adrf` and `uvicorn` added as runtime dependencies.
