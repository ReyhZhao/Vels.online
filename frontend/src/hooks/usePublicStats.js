import { useEffect, useState } from 'react';
import api from '../lib/axios';

/** Compact display form: 1_240 -> "1,240", 4_180_000 -> "4.2M". */
export function formatCount(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 100_000) return `${Math.round(value / 1_000)}K`;
  return value.toLocaleString('en-GB');
}

/**
 * Aggregated platform figures for the landing page, from the public (cached,
 * throttled) stats endpoint. Anything that fails to load renders as "—" rather
 * than as a made-up number.
 */
export function usePublicStats() {
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    api
      .get('/api/public/stats/')
      .then((res) => {
        if (cancelled) return;
        setStats(res.data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setStats(null);
        setError(err);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { stats, isLoading, error };
}
