import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

function SeverityBadge({ severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low
      }`}
    >
      {severity}
    </span>
  );
}

export default function AgentDetail() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const { selectedOrg, isLoading: orgLoading } = useOrganization();

  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchFirstPage = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(
        `/api/security/agents/${agentId}/events/?org=${slug}&offset=0&limit=100`
      );
      setEvents(res.data.events);
      setTotal(res.data.total);
    } catch {
      setError('Failed to load events.');
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    if (selectedOrg) fetchFirstPage(selectedOrg.slug);
  }, [selectedOrg, fetchFirstPage]);

  async function handleShowMore() {
    if (!selectedOrg || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await api.get(
        `/api/security/agents/${agentId}/events/?org=${selectedOrg.slug}&offset=${events.length}&limit=100`
      );
      setEvents((prev) => [...prev, ...res.data.events]);
      setTotal(res.data.total);
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleRefresh() {
    if (!selectedOrg || refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/security/dashboard/refresh/', {
        org: selectedOrg.slug,
        agent_id: agentId,
      });
      await fetchFirstPage(selectedOrg.slug);
    } finally {
      setRefreshing(false);
    }
  }

  if (orgLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!selectedOrg) return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/security')}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Fleet
          </button>
          <h1 className="text-2xl font-semibold text-foreground">Agent {agentId}</h1>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">
            Security Events{' '}
            <span className="font-normal text-muted-foreground">(last 24 h)</span>
          </h2>
          {total > 0 && (
            <span className="text-xs text-muted-foreground">
              Showing {events.length} of {total}
            </span>
          )}
        </div>

        {loading ? (
          <p className="py-4 text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Timestamp
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Severity
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Rule
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-4 py-8 text-center text-muted-foreground">
                        No events in the last 24 hours.
                      </td>
                    </tr>
                  ) : (
                    events.map((event, idx) => (
                      <tr
                        key={`${event.timestamp}-${idx}`}
                        className="border-b border-border last:border-0"
                      >
                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                          {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <SeverityBadge severity={event.severity} />
                        </td>
                        <td className="px-4 py-3 text-foreground">{event.rule_description}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {total > events.length && (
              <div className="flex justify-center pt-2">
                <button
                  onClick={handleShowMore}
                  disabled={loadingMore}
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
                >
                  {loadingMore ? 'Loading…' : `Show more (${total - events.length} remaining)`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
