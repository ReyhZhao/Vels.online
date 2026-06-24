import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../lib/axios';
import { parseSSEChunk } from '../lib/parseSSE';

/**
 * Incident Presence client (PRD #605, ADR-0028).
 *
 * Owns one long-lived SSE connection to the per-incident presence roster and the
 * outbound activity/lock POST path. Staff-only — pass `enabled: false` for
 * non-staff so no stream is ever opened and the roster stays empty.
 *
 * Lifecycle:
 *  - Page Visibility: a hidden tab tears the stream down (the server drops the
 *    actor + releases any held lock in its `finally`); re-focus re-opens it.
 *  - Transparent reconnect after a network blip.
 *  - Fail-open: if the backend is unreachable the roster is simply empty, the
 *    activity POSTs no-op, and lock acquisition is treated as granted — presence
 *    never blocks the page or comment editing.
 *
 * Returns `{ roster, setActivity, acquireLock, refreshLock, setViewing }`.
 */
export function useIncidentPresence(displayId, { enabled = true } = {}) {
  const [roster, setRoster] = useState([]);
  const abortRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);

  const teardown = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!enabled || !displayId) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    if (abortRef.current) return; // already connected

    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const response = await fetch(`/api/incidents/${displayId}/presence/`, {
          method: 'GET',
          credentials: 'include',
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const buf = { remainder: '' };
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const events = parseSSEChunk(decoder.decode(value, { stream: true }), buf);
          for (const ev of events) {
            if (ev.event === 'roster' && Array.isArray(ev.data)) {
              setRoster(ev.data);
            }
          }
        }
      } catch {
        // swallow — fail open
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        // Reconnect after a blip, unless intentionally torn down / hidden / unmounted.
        if (
          mountedRef.current && enabled && !controller.signal.aborted &&
          !(typeof document !== 'undefined' && document.hidden)
        ) {
          reconnectRef.current = setTimeout(() => connect(), 2000);
        }
      }
    })();
  }, [displayId, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) {
      setRoster([]);
      return undefined;
    }
    connect();

    function onVisibility() {
      if (document.hidden) {
        teardown();
        setRoster([]);
      } else {
        connect();
      }
    }
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      mountedRef.current = false;
      document.removeEventListener('visibilitychange', onVisibility);
      teardown();
    };
  }, [displayId, enabled, connect, teardown]);

  const post = useCallback(async (activity, target = null) => {
    if (!enabled || !displayId) return { ok: true };
    try {
      const res = await api.post(`/api/incidents/${displayId}/presence/`, { activity, target });
      return res.data ?? { ok: true };
    } catch (err) {
      if (err.response?.status === 409) {
        return { granted: false, holder: err.response.data?.holder };
      }
      // Fail open on any other error.
      return { ok: true, failedOpen: true };
    }
  }, [displayId, enabled]);

  const setActivity = useCallback((activity, target = null) => post(activity, target), [post]);
  const setViewing = useCallback(() => post('viewing', null), [post]);

  const acquireLock = useCallback(async (commentId) => {
    const res = await post('editing', commentId);
    if (res.granted === false) return { granted: false, holder: res.holder };
    return { granted: true };
  }, [post]);

  // Keystroke refresh — same POST; the server refreshes the idle window if it's ours.
  const refreshLock = useCallback((commentId) => post('editing', commentId), [post]);

  return { roster, setActivity, setViewing, acquireLock, refreshLock };
}

export default useIncidentPresence;
