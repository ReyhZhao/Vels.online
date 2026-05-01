import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import { useStatus } from './useStatus';

const UP_MONITOR = { name: 'API', status: 'up', uptime_ratio: '99.99', response_time: '120' };
const DOWN_MONITOR = { name: 'API', status: 'down', uptime_ratio: '95.00', response_time: '0' };
const DEGRADED_MONITOR = { name: 'API', status: 'seems_down', uptime_ratio: '98.00', response_time: '500' };

describe('useStatus', () => {
  beforeEach(() => vi.clearAllMocks());

  it('starts in loading state with unknown status', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useStatus());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.overallStatus).toBe('unknown');
  });

  it('returns operational when all monitors are up', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR] });
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.overallStatus).toBe('operational');
    expect(result.current.monitors).toHaveLength(1);
  });

  it('returns outage when any monitor is down', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR, DOWN_MONITOR] });
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.overallStatus).toBe('outage');
  });

  it('returns degraded when any monitor seems_down', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR, DEGRADED_MONITOR] });
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.overallStatus).toBe('degraded');
  });

  it('returns unknown and sets error when fetch fails', async () => {
    api.get.mockRejectedValue(new Error('Network error'));
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.overallStatus).toBe('unknown');
    expect(result.current.error).toBeTruthy();
  });

  it('returns unknown when monitor list is empty', async () => {
    api.get.mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.overallStatus).toBe('unknown');
  });

  it('polls again after 60 seconds', async () => {
    vi.useFakeTimers();
    api.get.mockResolvedValue({ data: [UP_MONITOR] });
    renderHook(() => useStatus());
    await act(() => Promise.resolve());
    expect(api.get).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(api.get).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it('exposes a refresh function that re-fetches', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR] });
    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const callsBefore = api.get.mock.calls.length;
    act(() => result.current.refresh());
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(callsBefore + 1));
  });

  it('forceRefresh calls POST /api/status/refresh/ and updates monitors', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR] });
    const freshMonitor = { ...UP_MONITOR, logs: [{ datetime: '2026-01-01T00:00:00Z', type: 'down', duration_seconds: 60 }] };
    api.post.mockResolvedValue({ data: [freshMonitor] });

    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.forceRefresh());
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));

    expect(api.post).toHaveBeenCalledWith('/api/status/refresh/');
    expect(result.current.monitors[0].logs).toHaveLength(1);
  });

  it('forceRefresh sets isRefreshing while in flight', async () => {
    api.get.mockResolvedValue({ data: [UP_MONITOR] });
    let resolve;
    api.post.mockReturnValue(new Promise((r) => { resolve = r; }));

    const { result } = renderHook(() => useStatus());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.forceRefresh());
    expect(result.current.isRefreshing).toBe(true);

    await act(() => { resolve({ data: [UP_MONITOR] }); });
    expect(result.current.isRefreshing).toBe(false);
  });
});
