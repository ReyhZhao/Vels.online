// useAttackStream — consumes the Live Attack Map SSE stream (PRD #594, ADR-0027).
//
// Mirrors the Hunt streaming idiom (lib/parseSSE.streamSSE over fetch with cookie
// credentials) so the codebase keeps one streaming pattern, not two. On connect it
// passes ?after=-1 to receive the buffer backfill (so the map paints immediately),
// tracks the last seq, and reconnects with ?after=<seq> on drop so it resumes where
// it left off rather than replaying from scratch. Exposes `events` (the arc buffer)
// and `stats` (the panel aggregates).
//
// Paced release (#698): the producer appends a whole ~10s window of attacks to the
// buffer at once, so the SSE tail delivers each tick as a burst. Releasing that burst
// into `events` in one update makes every arc launch on the same frame — a flood, then
// ~10s of dead air. Instead, live arrivals are queued and dripped out in seq order over
// time so the map animates continuously. The cold-join/reconnect backfill is exempt: it
// arrives in a tight burst right after connect and is flushed immediately as recent
// history rather than dripped. A pathologically large live burst also flushes at once
// so the queue can never lag arbitrarily far behind real arrivals.
import { useEffect, useRef, useState } from 'react';
import { streamSSE } from '../lib/parseSSE';

const MAX_EVENTS = 500; // matches the server buffer cap; arcs older than this fall off

// Pacing tunables (exported for tests).
export const BACKFILL_GRACE_MS = 600; // arcs within this of (re)connect are backfill → flush now
export const FLUSH_THRESHOLD = 100;   // a live burst this large flushes at once (no backlog)
export const SPREAD_MS = 8000;        // aim to spread a live batch across ~8s (< the ~10s tick)
export const MIN_INTERVAL_MS = 60;    // fastest drip, so big bursts still clear in a few seconds
export const MAX_INTERVAL_MS = 700;   // slowest drip, so a lone arc still appears promptly

export default function useAttackStream({ reconnectDelay = 1500 } = {}) {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [connected, setConnected] = useState(false);
  const lastSeq = useRef(-1);
  // Paced-release state: arcs received but not yet shown, and the drip timer.
  const pendingRef = useRef([]);
  const releaseTimerRef = useRef(null);
  const connectedAtRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    let closed = false;
    let timer = null;

    function appendEvents(batch) {
      if (!batch.length) return;
      setEvents((prev) => {
        const next = [...prev, ...batch];
        return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
      });
    }

    // Drip pending arcs into `events`. During the post-connect grace window (backfill)
    // or under a very large backlog, flush everything at once; otherwise release a single
    // arc and reschedule with an interval that shrinks as the backlog grows — so the map
    // keeps moving between ticks yet never falls far behind.
    function release() {
      releaseTimerRef.current = null;
      if (closed) return;
      const queue = pendingRef.current;
      if (queue.length === 0) return;
      const flushAll =
        Date.now() - connectedAtRef.current < BACKFILL_GRACE_MS ||
        queue.length >= FLUSH_THRESHOLD;
      appendEvents(flushAll ? queue.splice(0, queue.length) : queue.splice(0, 1));
      if (queue.length > 0) {
        const wait = flushAll
          ? 0
          : Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, SPREAD_MS / queue.length));
        releaseTimerRef.current = setTimeout(release, wait);
      }
    }

    function enqueueArc(arc) {
      pendingRef.current.push(arc);
      if (releaseTimerRef.current == null) releaseTimerRef.current = setTimeout(release, 0);
    }

    function handle(evt) {
      if (evt.event === 'arc' && evt.data) {
        if (evt.data.seq != null) lastSeq.current = Math.max(lastSeq.current, evt.data.seq);
        enqueueArc(evt.data);
      } else if (evt.event === 'stats' && evt.data) {
        setStats(evt.data);
      }
    }

    function connect() {
      if (closed) return;
      setConnected(true);
      // Mark the connect instant so the immediate backfill burst is flushed, not dripped.
      connectedAtRef.current = Date.now();
      streamSSE(
        `/api/attack-map/stream/?after=${lastSeq.current}`,
        { credentials: 'include', signal: controller.signal },
        handle,
      )
        .catch(() => {})
        .finally(() => {
          if (closed) return;
          setConnected(false);
          // Resume from the last seq we saw rather than replaying the whole buffer.
          timer = setTimeout(connect, reconnectDelay);
        });
    }

    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      if (releaseTimerRef.current) clearTimeout(releaseTimerRef.current);
      releaseTimerRef.current = null;
      controller.abort();
    };
  }, [reconnectDelay]);

  return { events, stats, connected };
}
