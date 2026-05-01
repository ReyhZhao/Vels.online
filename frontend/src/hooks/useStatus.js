import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../lib/axios';

const POLL_INTERVAL_MS = 60_000;

function deriveOverallStatus(monitors) {
  if (monitors.some((m) => m.status === 'down')) return 'outage';
  if (monitors.some((m) => m.status === 'seems_down' || m.status === 'paused')) return 'degraded';
  if (monitors.every((m) => m.status === 'up')) return 'operational';
  return 'unknown';
}

function applyMonitorData(data, setMonitors, setOverallStatus, setError) {
  setMonitors(data);
  setOverallStatus(data.length === 0 ? 'unknown' : deriveOverallStatus(data));
  setError(null);
}

export function useStatus() {
  const [monitors, setMonitors] = useState([]);
  const [overallStatus, setOverallStatus] = useState('unknown');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const refresh = useCallback(() => {
    api
      .get('/api/status/')
      .then((res) => {
        applyMonitorData(res.data, setMonitors, setOverallStatus, setError);
      })
      .catch((err) => {
        setError(err);
        setOverallStatus('unknown');
      })
      .finally(() => setIsLoading(false));
  }, []);

  const forceRefresh = useCallback(() => {
    setIsRefreshing(true);
    api
      .post('/api/status/refresh/')
      .then((res) => {
        applyMonitorData(res.data, setMonitors, setOverallStatus, setError);
      })
      .catch((err) => {
        setError(err);
      })
      .finally(() => setIsRefreshing(false));
  }, []);

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [refresh]);

  return { monitors, overallStatus, isLoading, isRefreshing, error, refresh, forceRefresh };
}
