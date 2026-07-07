import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../lib/api';
import type { Paginated } from '../lib/types';

interface PagedListState<T> {
  items: T[];
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  refresh: () => void;
  loadMore: () => void;
  count: number;
}

type Params = Record<string, string | number | boolean | undefined>;

/**
 * Paged fetch over the backend's standard pagination envelope
 * ({count, page, per_page, total_pages, results}); also accepts endpoints
 * that return a plain array (treated as a single page).
 *
 * Refetches from page 1 whenever `path` or the serialized params change;
 * `loadMore` appends the next page until total_pages is reached.
 */
export function usePagedList<T>(path: string, params: Params = {}): PagedListState<T> {
  const [items, setItems] = useState<T[]>([]);
  const [count, setCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pageRef = useRef(1);
  const totalPagesRef = useRef(1);
  const busyRef = useRef(false);
  const generationRef = useRef(0);

  const paramsKey = JSON.stringify(params);

  const fetchPage = useCallback(
    async (page: number, { refreshing = false } = {}) => {
      if (busyRef.current) return;
      busyRef.current = true;
      const generation = ++generationRef.current;
      if (refreshing) setIsRefreshing(true);
      else if (page === 1) setIsLoading(true);
      try {
        const res = await api.get(path, { params: { ...JSON.parse(paramsKey), page } });
        if (generation !== generationRef.current) return;
        const data = res.data as Paginated<T> | T[];
        if (Array.isArray(data)) {
          setItems(data);
          setCount(data.length);
          totalPagesRef.current = 1;
        } else {
          setItems((prev) => (page === 1 ? data.results : [...prev, ...data.results]));
          setCount(data.count);
          totalPagesRef.current = data.total_pages ?? 1;
        }
        pageRef.current = page;
        setError(null);
      } catch (err: any) {
        if (generation !== generationRef.current) return;
        setError(err?.response?.data?.detail ?? 'Could not load data.');
      } finally {
        busyRef.current = false;
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [path, paramsKey],
  );

  useEffect(() => {
    pageRef.current = 1;
    fetchPage(1);
  }, [fetchPage]);

  const refresh = useCallback(() => {
    fetchPage(1, { refreshing: true });
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (pageRef.current < totalPagesRef.current) {
      fetchPage(pageRef.current + 1);
    }
  }, [fetchPage]);

  return { items, isLoading, isRefreshing, error, refresh, loadMore, count };
}
