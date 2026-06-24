// useIncidentPresence — per-incident presence roster over SSE (PRD #605, ADR-0028).
import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: { ok: true } }) },
}));

import useIncidentPresence from './useIncidentPresence';

const ROSTER = [
  {
    actor_key: 'user:1',
    display_name: 'Alice Smith',
    actor_kind: 'human',
    activity: 'viewing',
    target: null,
  },
];

/**
 * Build a fake fetch that:
 *  1. Returns a first chunk containing an SSE roster event.
 *  2. Then hangs on the second read() until the AbortController fires.
 *
 * This matches the real stream: an initial snapshot is emitted immediately,
 * then the connection stays open and self-heals via the AbortError path when
 * the tab hides (teardown aborts the controller).
 */
function makeHangingFetch(rosterData) {
  return vi.fn().mockImplementation((_url, options) => {
    const signal = options?.signal;
    const sseText = `event: roster\ndata: ${JSON.stringify(rosterData)}\n\n`;
    const bytes = new TextEncoder().encode(sseText);
    let phase = 0;
    return Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader() {
          return {
            read() {
              if (phase === 0) {
                phase = 1;
                return Promise.resolve({ done: false, value: bytes });
              }
              // Hang until the AbortController fires.
              return new Promise((_, reject) => {
                signal?.addEventListener(
                  'abort',
                  () => reject(new DOMException('Aborted', 'AbortError')),
                  { once: true },
                );
              });
            },
            releaseLock() {},
          };
        },
      },
    });
  });
}

describe('useIncidentPresence', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset visibility to visible before each test.
    Object.defineProperty(document, 'hidden', {
      value: false,
      configurable: true,
      writable: true,
    });
  });

  it('populates roster from SSE stream', async () => {
    global.fetch = makeHangingFetch(ROSTER);
    const { result } = renderHook(() => useIncidentPresence('INC-1', { enabled: true }));

    await waitFor(() => expect(result.current.roster).toHaveLength(1));
    expect(result.current.roster[0].display_name).toBe('Alice Smith');
    expect(result.current.roster[0].activity).toBe('viewing');
  });

  it('does not connect when enabled=false (non-staff gate)', () => {
    global.fetch = vi.fn();
    const { result } = renderHook(() => useIncidentPresence('INC-1', { enabled: false }));

    expect(fetch).not.toHaveBeenCalled();
    expect(result.current.roster).toEqual([]);
  });

  it('tears down stream on visibility-hidden and clears roster', async () => {
    global.fetch = makeHangingFetch(ROSTER);
    const { result } = renderHook(() => useIncidentPresence('INC-1', { enabled: true }));

    // Wait for the first roster snapshot.
    await waitFor(() => expect(result.current.roster).toHaveLength(1));

    // Simulate the tab going into the background.
    act(() => {
      Object.defineProperty(document, 'hidden', {
        value: true,
        configurable: true,
        writable: true,
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Roster must be cleared immediately on teardown.
    await waitFor(() => expect(result.current.roster).toEqual([]));
  });

  it('fails open to empty roster when the stream is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('NetworkError'));
    const { result, unmount } = renderHook(() =>
      useIncidentPresence('INC-1', { enabled: true }),
    );

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    // Roster stays empty — no error surfaced to the caller.
    expect(result.current.roster).toEqual([]);
    // Unmount to cancel the pending 2s reconnect timer.
    unmount();
  });
});
