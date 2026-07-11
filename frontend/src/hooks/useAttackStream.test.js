import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../lib/parseSSE', () => ({ streamSSE: vi.fn() }));
import { streamSSE } from '../lib/parseSSE';
import useAttackStream, { BACKFILL_GRACE_MS, MAX_INTERVAL_MS } from './useAttackStream';

describe('useAttackStream', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.useRealTimers());

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

  it('flushes the cold-join backfill burst at once, preserving order (#698)', async () => {
    // A backfill of many arcs arrives in one burst right after connect; it should paint
    // as recent history immediately, not drip out slowly.
    streamSSE.mockImplementation((url, opts, onEvent) => {
      for (let seq = 0; seq < 40; seq += 1) onEvent({ event: 'arc', data: { seq, level: 5 } });
      return new Promise(() => {});
    });
    const { result } = renderHook(() => useAttackStream());
    await waitFor(() => expect(result.current.events).toHaveLength(40));
    expect(result.current.events.map((e) => e.seq)).toEqual([...Array(40).keys()]);
  });

  it('drips live arcs one at a time in seq order after the backfill window (#698)', async () => {
    vi.useFakeTimers();
    let emit;
    streamSSE.mockImplementation((url, opts, onEvent) => {
      emit = onEvent;
      return new Promise(() => {}); // stay open
    });
    const { result } = renderHook(() => useAttackStream());

    // Let the post-connect backfill grace window elapse (no backfill emitted here).
    await act(async () => { await vi.advanceTimersByTimeAsync(BACKFILL_GRACE_MS + 50); });

    // A producer tick delivers a burst of 4 live arcs at once.
    act(() => {
      [10, 11, 12, 13].forEach((seq) => emit({ event: 'arc', data: { seq, level: 5 } }));
    });

    // The burst does NOT land on one frame: the first arc drips out, the rest follow.
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.events.map((e) => e.seq)).toEqual([10]);

    await act(async () => { await vi.advanceTimersByTimeAsync(MAX_INTERVAL_MS); });
    expect(result.current.events).toHaveLength(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(MAX_INTERVAL_MS * 3); });
    expect(result.current.events.map((e) => e.seq)).toEqual([10, 11, 12, 13]);
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
