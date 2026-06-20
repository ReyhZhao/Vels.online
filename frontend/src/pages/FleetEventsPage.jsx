import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useSearchParams, useNavigate } from 'react-router-dom';
import EventSlideOver from '../components/EventSlideOver';
import PromoteToIncidentButton from '../components/PromoteToIncidentButton';

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];

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

function eventSourceRef(event) {
  return {
    event_id: event.id,
    agent_id: event.agent_id,
    agent_name: event.agent_name,
    rule_id: event.rule_id,
    rule_description: event.rule_description,
    level: event.level,
  };
}

export default function FleetEventsPage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const navigate = useNavigate();
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
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkForm, setBulkForm] = useState(null);
  const [bulkPreparing, setBulkPreparing] = useState(false);
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkError, setBulkError] = useState(null);

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const ids = events.map(e => e.id);
    const allSelected = ids.length > 0 && ids.every(id => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(ids));
  }

  async function handleBulkPromote() {
    const sel = events.filter(e => selectedIds.has(e.id));
    if (sel.length === 0) return;
    setBulkPreparing(true);
    setBulkError(null);
    try {
      const primary = sel[0];
      const res = await api.post('/api/incidents/promote/', {
        source_kind: 'wazuh_event',
        source_ref: eventSourceRef(primary),
      });
      const fp = res.data.form_payload;
      const lines = sel.map(e => `- ${e.agent_name} | ${e.rule_id} | ${e.rule_description}`).join('\n');
      setBulkForm({
        ...fp,
        title: sel.length > 1 ? `${sel.length} Wazuh events` : fp.title,
        description: `${fp.description}\n\nIncluded events (${sel.length}):\n${lines}`,
      });
    } catch (err) {
      setBulkError(err.response?.data?.detail || 'Failed to prepare incident.');
    } finally {
      setBulkPreparing(false);
    }
  }

  async function handleBulkSubmit(e) {
    e.preventDefault();
    if (!selectedOrg) return;
    setBulkSubmitting(true);
    setBulkError(null);
    try {
      const res = await api.post('/api/incidents/promote/', {
        ...bulkForm,
        commit: true,
        org: selectedOrg.slug,
      });
      setBulkForm(null);
      setSelectedIds(new Set());
      navigate(`/incidents/${res.data.display_id}`);
    } catch (err) {
      setBulkError(err.response?.data?.detail || 'Failed to create incident.');
    } finally {
      setBulkSubmitting(false);
    }
  }

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

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : events.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No events found.</p>
        ) : events.map((event, idx) => (
          <div key={`${event.id}-${idx}`} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedIds.has(event.id)}
                onChange={() => toggleSelect(event.id)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                aria-label={`Select event ${event.rule_id}`}
              />
              <span className="text-sm font-medium text-foreground">{event.agent_name}</span>
              <span className="ml-auto"><SeverityBadge severity={event.severity} /></span>
            </div>
            <p className="text-sm text-foreground leading-snug cursor-pointer" onClick={() => handleRowClick(event)}>{event.rule_description}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-mono">{event.rule_id}</span>
              <span className="ml-auto">{event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  checked={events.length > 0 && events.every(e => selectedIds.has(e.id))}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Timestamp</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No events found.</td>
              </tr>
            ) : (
              events.map((event, idx) => (
                <tr
                  key={`${event.id}-${idx}`}
                  className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                >
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(event.id)}
                      onChange={() => toggleSelect(event.id)}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                      aria-label={`Select event ${event.rule_id}`}
                    />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground cursor-pointer" onClick={() => handleRowClick(event)}>{event.agent_name}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap cursor-pointer" onClick={() => handleRowClick(event)}>
                    {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 cursor-pointer" onClick={() => handleRowClick(event)}>
                    <SeverityBadge severity={event.severity} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground cursor-pointer" onClick={() => handleRowClick(event)}>{event.rule_id}</td>
                  <td className="px-4 py-3 text-foreground cursor-pointer" onClick={() => handleRowClick(event)}>{event.rule_description}</td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <PromoteToIncidentButton
                      sourceKind="wazuh_event"
                      sourceRef={eventSourceRef(event)}
                      orgSlug={selectedOrg?.slug}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bulk promote toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-4 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={handleBulkPromote}
            disabled={bulkPreparing}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {bulkPreparing ? 'Preparing…' : `Promote to incident (${selectedIds.size})`}
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      )}
      {bulkError && !bulkForm && <p className="text-sm text-red-600">{bulkError}</p>}

      {/* Bulk promote modal */}
      {bulkForm && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
          <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-5 mx-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Create Incident from {selectedIds.size} events</h2>
              <button onClick={() => setBulkForm(null)} className="text-sm text-muted-foreground hover:text-foreground">✕</button>
            </div>
            <form onSubmit={handleBulkSubmit} className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Title</label>
                <input
                  value={bulkForm.title}
                  onChange={e => setBulkForm(d => ({ ...d, title: e.target.value }))}
                  required
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Severity</label>
                <select
                  value={bulkForm.severity}
                  onChange={e => setBulkForm(d => ({ ...d, severity: e.target.value }))}
                  aria-label="Severity"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</label>
                <textarea
                  value={bulkForm.description}
                  onChange={e => setBulkForm(d => ({ ...d, description: e.target.value }))}
                  rows={5}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                />
              </div>
              {bulkError && <p className="text-sm text-red-600">{bulkError}</p>}
              <div className="flex justify-end gap-3 pt-1">
                <button type="button" onClick={() => setBulkForm(null)} disabled={bulkSubmitting}
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50">
                  Cancel
                </button>
                <button type="submit" disabled={bulkSubmitting || !bulkForm.title?.trim()}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
                  {bulkSubmitting ? 'Creating…' : 'Create incident'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

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
