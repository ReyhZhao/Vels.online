import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';

// Threat Hunting console (ADR-0015): list past/in-progress Hunts + a New Hunt composer.
// Staff-only; a Hunt is its own surface, not embedded in any incident view.

const STATUS_CLASSES = {
  created: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  scoping: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  scoping_running: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const LOOKBACKS = [7, 30, 90, 180];

// Statuses a hunt can be filtered by, and the in-flight ones that cannot be deleted
// (the worker is still writing to them — cancel first). Mirrors hunts.models.Hunt.
const STATUS_FILTERS = [
  'created', 'scoping', 'scoping_running', 'running', 'completed', 'cancelled', 'error',
];
const IN_FLIGHT = ['running', 'scoping_running'];

const SORT_COLUMNS = {
  status:    { label: 'Status',    defaultOrder: 'asc' },
  findings:  { label: 'Findings',  defaultOrder: 'desc' },
  incidents: { label: 'Incidents', defaultOrder: 'desc' },
  owner:     { label: 'Owner',     defaultOrder: 'asc' },
};

export default function ThreatHuntingPage() {
  const navigate = useNavigate();
  const [hunts, setHunts] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // List search + status filter (issue #508).
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // List sort + bulk selection (issue #581).
  const [sortKey, setSortKey] = useState(null);
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  // composer state
  const [seedKind, setSeedKind] = useState('question');
  const [seedText, setSeedText] = useState('');
  const [seedUrl, setSeedUrl] = useState('');
  const [scopeAll, setScopeAll] = useState(true);
  const [scopeOrgIds, setScopeOrgIds] = useState([]);
  const [lookback, setLookback] = useState(30);
  const [submitting, setSubmitting] = useState(false);

  const loadHunts = useCallback(async () => {
    try {
      const params = {};
      if (search.trim()) params.search = search.trim();
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get('/api/hunts/', { params });
      setHunts(data);
    } catch (e) {
      setError('Could not load hunts.');
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter]);

  // Debounce list reloads so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(loadHunts, 250);
    return () => clearTimeout(t);
  }, [loadHunts]);

  useEffect(() => {
    // include_infrastructure=1 surfaces the Infrastructure org as a selectable hunt
    // scope target (ADR-0017) — it stays out of every other org picker.
    api.get('/api/security/organizations/?include_infrastructure=1')
      .then(({ data }) => setOrgs(Array.isArray(data) ? data : (data.results || [])))
      .catch(() => {});
  }, []);

  async function deleteHunt(e, hunt) {
    e.stopPropagation(); // don't navigate into the row we're deleting
    if (!window.confirm(`Delete this hunt permanently?\n\n${hunt.title}`)) return;
    setError(null);
    try {
      await api.delete(`/api/hunts/${hunt.id}/`);
      setHunts((prev) => prev.filter((h) => h.id !== hunt.id));
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Could not delete hunt.');
    }
  }

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder(SORT_COLUMNS[key]?.defaultOrder ?? 'asc');
    }
  }

  const visible = useMemo(() => {
    if (!sortKey) return hunts;
    const dir = sortOrder === 'asc' ? 1 : -1;
    return [...hunts].sort((a, b) => {
      if (sortKey === 'findings') return ((a.finding_count || 0) - (b.finding_count || 0)) * dir;
      if (sortKey === 'incidents') return ((a.spawned_incident_count || 0) - (b.spawned_incident_count || 0)) * dir;
      if (sortKey === 'owner') return (a.owner_username || '').localeCompare(b.owner_username || '') * dir;
      return (a.status || '').localeCompare(b.status || '') * dir;
    });
  }, [hunts, sortKey, sortOrder]);

  // In-flight hunts (running / scoping_running) can't be deleted while the
  // worker is still writing to them, so they're never selectable for bulk delete.
  const deletableIds = visible.filter((h) => !IN_FLIGHT.includes(h.status)).map((h) => h.id);
  const allDeletableSelected = deletableIds.length > 0 && deletableIds.every((id) => selectedIds.has(id));
  const someDeletableSelected = deletableIds.some((id) => selectedIds.has(id));

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allDeletableSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        deletableIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds((prev) => new Set([...prev, ...deletableIds]));
    }
  }

  async function bulkDelete() {
    const targets = visible.filter((h) => selectedIds.has(h.id) && !IN_FLIGHT.includes(h.status));
    if (targets.length === 0) return;
    if (!window.confirm(`Delete ${targets.length} hunt${targets.length === 1 ? '' : 's'} permanently?`)) return;
    setBulkBusy(true);
    setError(null);
    for (const h of targets) {
      try {
        await api.delete(`/api/hunts/${h.id}/`);
        setHunts((prev) => prev.filter((x) => x.id !== h.id));
      } catch {
        setError('Could not delete one or more hunts.');
      }
    }
    setSelectedIds(new Set());
    setBulkBusy(false);
  }

  function SortHeader({ field }) {
    return (
      <th className="p-2">
        <button
          type="button"
          onClick={() => setSort(field)}
          className="flex items-center gap-1 font-medium hover:underline"
          aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
        >
          {SORT_COLUMNS[field].label}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await api.post('/api/hunts/', {
        seed_kind: seedKind,
        seed_text: seedKind === 'question' ? seedText : '',
        seed_url: seedKind === 'url' ? seedUrl : '',
        scope_all_orgs: scopeAll,
        scope_org_ids: scopeAll ? [] : scopeOrgIds,
        lookback_days: lookback,
      });
      navigate(`/hunting/${data.id}`);
    } catch (e2) {
      setError(e2.response?.data?.detail || 'Could not start hunt.');
      setSubmitting(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Threat Hunting</h1>

      <form onSubmit={submit} className="border rounded-lg p-4 space-y-3 dark:border-gray-700">
        <h2 className="font-medium">New Hunt</h2>

        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="radio" checked={seedKind === 'question'} onChange={() => setSeedKind('question')} />
            Question
          </label>
          <label className="flex items-center gap-1">
            <input type="radio" checked={seedKind === 'url'} onChange={() => setSeedKind('url')} />
            Report URL
          </label>
        </div>

        {seedKind === 'question' ? (
          <textarea
            className="w-full border rounded p-2 text-sm min-h-[8rem] resize-y dark:bg-gray-800 dark:border-gray-700"
            rows={6} placeholder="e.g. Are we exposed to the XYZ ransomware campaign?"
            value={seedText} onChange={(e) => setSeedText(e.target.value)}
          />
        ) : (
          <input
            className="w-full border rounded p-2 text-sm dark:bg-gray-800 dark:border-gray-700"
            type="url" placeholder="https://vendor.example/threat-report"
            value={seedUrl} onChange={(e) => setSeedUrl(e.target.value)}
          />
        )}

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={scopeAll} onChange={(e) => setScopeAll(e.target.checked)} />
            All organisations
          </label>
          {!scopeAll && (
            <select
              multiple value={scopeOrgIds.map(String)}
              onChange={(e) => setScopeOrgIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
              aria-label="Organisations to scope this hunt to"
              className="min-w-[12rem] rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          )}
          <label className="flex items-center gap-1">
            Lookback
            <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))}
                    className="border rounded p-1 dark:bg-gray-800 dark:border-gray-700">
              {LOOKBACKS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </label>
          <button type="submit" disabled={submitting}
                  className="ml-auto bg-blue-600 text-white rounded px-4 py-1.5 disabled:opacity-50">
            {submitting ? 'Starting…' : 'Start hunt'}
          </button>
        </div>
      </form>

      {error && <div className="text-sm text-red-600">{error}</div>}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          type="search" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search hunts…" aria-label="Search hunts"
          className="flex-1 min-w-[12rem] border rounded p-2 dark:bg-gray-800 dark:border-gray-700"
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
                className="border rounded p-2 dark:bg-gray-800 dark:border-gray-700">
          <option value="">All statuses</option>
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 border rounded-lg p-2 text-sm dark:border-gray-700">
          <span className="font-medium">{selectedIds.size} selected</span>
          <button
            type="button"
            onClick={bulkDelete}
            disabled={bulkBusy}
            aria-label="Delete selected"
            className="rounded border border-red-300 px-3 py-1 font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:hover:bg-red-900/20"
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            Clear
          </button>
        </div>
      )}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-gray-500">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-gray-500">
            {search.trim() || statusFilter ? 'No hunts match your filters.' : 'No hunts yet.'}
          </p>
        ) : visible.map((h) => (
          <div key={h.id} className="border rounded-lg p-3 space-y-2 dark:border-gray-700">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2 min-w-0">
                <input
                  type="checkbox"
                  checked={selectedIds.has(h.id)}
                  disabled={IN_FLIGHT.includes(h.status)}
                  onChange={() => toggleSelect(h.id)}
                  aria-label={`Select ${h.title}`}
                  className="mt-1 h-4 w-4 rounded disabled:opacity-40"
                />
                <button
                  type="button"
                  onClick={() => navigate(`/hunting/${h.id}`)}
                  className="text-left font-medium hover:underline truncate"
                >
                  {h.title}
                </button>
              </div>
              <span className={`shrink-0 px-2 py-0.5 rounded text-xs ${STATUS_CLASSES[h.status] || ''}`}>{h.status}</span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400">
              <span>{h.scope_all_orgs ? 'All orgs' : 'Selected'}</span>
              <span>Findings: {h.finding_count}</span>
              <span>Incidents: {h.spawned_incident_count}</span>
              <span>Owner: {h.owner_username || '—'}</span>
            </div>
            {!IN_FLIGHT.includes(h.status) && (
              <button onClick={(e) => deleteHunt(e, h)} aria-label="Delete hunt" className="text-xs text-red-600 hover:text-red-700">
                Delete
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block border rounded-lg dark:border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800 text-left">
            <tr>
              <th className="p-2 w-8">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={allDeletableSelected}
                  ref={(el) => { if (el) el.indeterminate = someDeletableSelected && !allDeletableSelected; }}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded"
                />
              </th>
              <th className="p-2">Seed</th>
              <th className="p-2">Scope</th>
              <SortHeader field="status" />
              <SortHeader field="findings" />
              <SortHeader field="incidents" />
              <SortHeader field="owner" />
              <th className="p-2 w-0" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="p-4 text-center text-gray-500">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={8} className="p-4 text-center text-gray-500">
                {search.trim() || statusFilter ? 'No hunts match your filters.' : 'No hunts yet.'}
              </td></tr>
            ) : visible.map((h) => (
              <tr key={h.id} className="border-t dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                  onClick={() => navigate(`/hunting/${h.id}`)}>
                <td className="p-2 w-8" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(h.id)}
                    disabled={IN_FLIGHT.includes(h.status)}
                    onChange={() => toggleSelect(h.id)}
                    aria-label={`Select ${h.title}`}
                    className="h-4 w-4 rounded disabled:opacity-40"
                  />
                </td>
                <td className="p-2 max-w-xs truncate">{h.title}</td>
                <td className="p-2">{h.scope_all_orgs ? 'All orgs' : 'Selected'}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${STATUS_CLASSES[h.status] || ''}`}>{h.status}</span>
                </td>
                <td className="p-2">{h.finding_count}</td>
                <td className="p-2">{h.spawned_incident_count}</td>
                <td className="p-2">{h.owner_username || '—'}</td>
                <td className="p-2 text-right">
                  {!IN_FLIGHT.includes(h.status) && (
                    <button onClick={(e) => deleteHunt(e, h)}
                            aria-label="Delete hunt"
                            className="text-red-600 hover:text-red-700 px-2">
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
