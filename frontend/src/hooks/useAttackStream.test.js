import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/parseSSE', () => ({ streamSSE: vi.fn() }));
import { streamSSE } from '../lib/parseSSE';
import useAttackStream from './useAttackStream';

describe('useAttackStream', () => {
  beforeEach(() => vi.clearAllMocks());

  it('connects with after=-1 and backfills arcs + stats, then tails', async () => {
    streamSSE.mockImplementation((url, opts, onEvent) => {
      // Cold-join backfill: stats then two arcs.
      onEvent({ event: 'stats', data: { per_minute: 4, top_countries: [['China', 3]] } });
      onEvent({ event: 'arc', data: { seq: 0, level: 7, srcCountry: 'China' } });
      onEvent({ event: 'arc', data: { seq: 1, level: 12, srcCountry: 'Russia' } });
      return new Promise(() => {}); // stay open (no reconnect)
    });

    const { result } = renderHook(() => useAttackStream());

    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(streamSSE.mock.calls[0][0]).toContain('after=-1');
    expect(result.current.events.map((e) => e.seq)).toEqual([0, 1]);
    expect(result.current.stats.per_minute).toBe(4);
  });

  it('reconnects from the last seq after the stream drops (#595)', async () => {
    let firstCall = true;
    streamSSE.mockImplementation((url, opts, onEvent) => {
      if (firstCall) {
        firstCall = false;
        onEvent({ event: 'arc', data: { seq: 5, level: 9, srcCountry: 'Brazil' } });
        return Promise.resolve(); // stream ends → triggers reconnect
      }
      return new Promise(() => {});
    });

    const { result } = renderHook(() => useAttackStream({ reconnectDelay: 5 }));

    await waitFor(() => expect(streamSSE).toHaveBeenCalledTimes(2));
    // The reconnect resumes from the last seq seen, not the whole buffer.
    expect(streamSSE.mock.calls[1][0]).toContain('after=5');
  });

  it('aborts the stream on unmount', async () => {
    let signal;
    streamSSE.mockImplementation((url, opts) => {
      signal = opts.signal;
      return new Promise(() => {});
    });
    const { unmount } = renderHook(() => useAttackStream());
    await waitFor(() => expect(signal).toBeDefined());
    expect(signal.aborted).toBe(false);
    act(() => unmount());
    expect(signal.aborted).toBe(true);
  });
});
