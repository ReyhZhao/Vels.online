// useAttackStream — consumes the Live Attack Map SSE stream (PRD #594, ADR-0027).
//
// Mirrors the Hunt streaming idiom (lib/parseSSE.streamSSE over fetch with cookie
// credentials) so the codebase keeps one streaming pattern, not two. On connect it
// passes ?after=-1 to receive the buffer backfill (so the map paints immediately),
// tracks the last seq, and reconnects with ?after=<seq> on drop so it resumes where
// it left off rather than replaying from scratch. Exposes `events` (the arc buffer)
// and `stats` (the panel aggregates).
import { useEffect, useRef, useState } from 'react';
import { streamSSE } from '../lib/parseSSE';

const MAX_EVENTS = 500; // matches the server buffer cap; arcs older than this fall off

export default function useAttackStream({ reconnectDelay = 1500 } = {}) {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [connected, setConnected] = useState(false);
  const lastSeq = useRef(-1);

  useEffect(() => {
    const controller = new AbortController();
    let closed = false;
    let timer = null;

    function handle(evt) {
      if (evt.event === 'arc' && evt.data) {
        if (evt.data.seq != null) lastSeq.current = Math.max(lastSeq.current, evt.data.seq);
        setEvents((prev) => {
          const next = [...prev, evt.data];
          return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
        });
      } else if (evt.event === 'stats' && evt.data) {
        setStats(evt.data);
      }
    }

    function connect() {
      if (closed) return;
      setConnected(true);
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
      controller.abort();
    };
  }, [reconnectDelay]);

  return { events, stats, connected };
}
