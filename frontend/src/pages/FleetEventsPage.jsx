import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useSearchParams } from 'react-router-dom';
import EventSlideOver from '../components/EventSlideOver';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

const TIME_RANGES = [
  { label: '5m',  value: '5' },
  { label: '15m', value: '15' },
  { label: '30m', value: '30' },
  { label: '1h',  value: '60' },
  { label: '6h',  value: '360' },
  { label: '24h', value: '1440' },
  { label: '7d',  value: '10080' },
  { label: '30d', value: '43200' },
];

const LIMIT = 100;

function StatCard({ label, value, colorClass }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${colorClass ?? 'text-foreground'}`}>
        {value ?? '—'}
      </p>
    </div>
  );
}

function SeverityBadge({ severity }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low}`}>
      {severity}
    </span>
  );
}

export default function FleetEventsPage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [searchParams, setSearchParams] = useSearchParams();

  const severityParam = searchParams.get('severity') || '';
  const minutesParam  = searchParams.get('minutes') || '1440';
  const searchParam   = searchParams.get('search') || '';
  const agentParam    = searchParams.get('agent') || '';

  const activeSeverities = severityParam ? severityParam.split(',').filter(Boolean) : [];

  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [selectedAgentId, setSelectedAgentId] = useState(null);

  function updateParams(updates) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      Object.entries(updates).forEach(([k, v]) => {
        if (v === null || v === '') next.delete(k);
        else next.set(k, v);
      });
      return next;
    });
  }

  function toggleSeverity(sev) {
    const next = activeSeverities.includes(sev)
      ? activeSeverities.filter(s => s !== sev)
      : [...activeSeverities, sev];
    updateParams({ severity: next.join(',') || null });
  }

  const fetchAgents = useCallback(async (slug) => {
    try {
      const res = await api.get(`/api/security/agents/?org=${slug}`);
      setAgents(res.data);
    } catch {}
  }, []);

  const fetchEvents = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    setEvents([]);
    try {
      const params = new URLSearchParams();
      params.set('org', slug);
      params.set('minutes', minutesParam);
      params.set('offset', '0');
      params.set('limit', String(LIMIT));
      if (severityParam) params.set('severity', severityParam);
      if (searchParam)   params.set('search', searchParam);
      if (agentParam)    params.set('agent', agentParam);

      const res = await api.get(`/api/security/events/?${params}`);
      setEvents(res.data.events);
      setTotal(res.data.total);
      setStats(res.data.stats);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load events.');
    } finally {
      setLoading(false);
    }
  }, [minutesParam, severityParam, searchParam, agentParam]);

  useEffect(() => {
    if (selectedOrg) {
      fetchAgents(selectedOrg.slug);
      fetchEvents(selectedOrg.slug);
    }
  }, [selectedOrg, fetchAgents, fetchEvents]);

  async function handleShowMore() {
    if (loadingMore || !selectedOrg) return;
    setLoadingMore(true);
    try {
      const params = new URLSearchParams();
      params.set('org', selectedOrg.slug);
      params.set('minutes', minutesParam);
      params.set('offset', String(events.length));
      params.set('limit', String(LIMIT));
      if (severityParam) params.set('severity', severityParam);
      if (searchParam)   params.set('search', searchParam);
      if (agentParam)    params.set('agent', agentParam);

      const res = await api.get(`/api/security/events/?${params}`);
      setEvents(prev => [...prev, ...res.data.events]);
      setTotal(res.data.total);
    } finally {
      setLoadingMore(false);
    }
  }

  function handleRowClick(event) {
    setSelectedEventId(event.id);
    setSelectedAgentId(event.agent_id);
  }

  if (orgLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!selectedOrg) return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;

  const hasFilters = severityParam || minutesParam !== '1440' || searchParam || agentParam;

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Events — {selectedOrg.name}</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Critical"        value={stats?.critical}   colorClass="text-red-600 dark:text-red-400" />
        <StatCard label="High"            value={stats?.high}       colorClass="text-orange-600 dark:text-orange-400" />
        <StatCard label="Medium"          value={stats?.medium}     colorClass="text-yellow-600 dark:text-yellow-400" />
        <StatCard label="Low"             value={stats?.low}        colorClass="text-blue-600 dark:text-blue-400" />
        <StatCard label="Total Events"    value={stats?.total} />
        <StatCard label="Events (24h)"    value={stats?.events_24h} />
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {['critical', 'high', 'medium', 'low'].map(sev => (
          <button
            key={sev}
            onClick={() => toggleSeverity(sev)}
            className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
              activeSeverities.includes(sev)
                ? `${SEVERITY_CLASSES[sev]} border-transparent`
                : 'border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            {sev}
          </button>
        ))}

        {/* Time range selector */}
        <div className="flex rounded-md border border-border overflow-hidden">
          {TIME_RANGES.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => updateParams({ minutes: value === '1440' ? null : value })}
              aria-pressed={minutesParam === value}
              className={`px-2 py-1 text-xs font-medium transition-colors ${
                minutesParam === value
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Agent dropdown */}
        <div className="relative">
          <select
            value={agentParam}
            onChange={e => updateParams({ agent: e.target.value || null })}
            className="rounded-md border border-border bg-background px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring appearance-none pr-8"
            aria-label="Filter by agent"
          >
            <option value="">All agents</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">▾</span>
        </div>

        <input
          type="text"
          placeholder="Search rules…"
          value={searchParam}
          onChange={e => updateParams({ search: e.target.value || null })}
          className="rounded-md border border-border bg-background px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        {hasFilters && (
          <button
            onClick={() => setSearchParams({})}
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Events table */}
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Timestamp</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No events found.</td>
              </tr>
            ) : (
              events.map((event, idx) => (
                <tr
                  key={`${event.id}-${idx}`}
                  onClick={() => handleRowClick(event)}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                >
                  <td className="px-4 py-3 text-muted-foreground">{event.agent_name}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={event.severity} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{event.rule_id}</td>
                  <td className="px-4 py-3 text-foreground">{event.rule_description}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Show more */}
      {!loading && total > events.length && (
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

      <EventSlideOver
        agentId={selectedAgentId}
        orgSlug={selectedOrg.slug}
        eventId={selectedEventId}
        onClose={() => { setSelectedEventId(null); setSelectedAgentId(null); }}
      />
    </div>
  );
}
