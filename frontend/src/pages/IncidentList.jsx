import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import SlideOver from '../components/SlideOver';
import SLAPill from '../components/SLAPill';
import CreateIncidentModal from '../components/CreateIncidentModal';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const TLP_CLASSES = {
  white: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  red:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const STATE_CLASSES = {
  new:         'text-blue-600 dark:text-blue-400',
  triaged:     'text-purple-600 dark:text-purple-400',
  in_progress: 'text-yellow-600 dark:text-yellow-400',
  on_hold:     'text-orange-600 dark:text-orange-400',
  resolved:    'text-green-600 dark:text-green-400',
  closed:      'text-muted-foreground',
};

const TABS = [
  { key: 'my_queue',   label: 'My Queue' },
  { key: 'unassigned', label: 'Unassigned' },
  { key: '',           label: 'All' },
];

const STATE_OPTIONS    = ['new', 'triaged', 'in_progress', 'on_hold', 'resolved', 'closed'];
const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];
const TLP_OPTIONS      = ['white', 'green', 'amber', 'red'];

const EMPTY_DATA = { count: 0, page: 1, per_page: 25, total_pages: 1, results: [] };

export default function IncidentList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData]         = useState(EMPTY_DATA);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const [preview, setPreview]   = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const pollRef = useRef(null);

  const activeTab = searchParams.get('tab') || '';

  const fetchIncidents = useCallback(async (params, { silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const res = await api.get('/api/incidents/', { params });
      setData(res.data);
    } catch (err) {
      if (!silent) setError(err.response?.data?.detail || 'Failed to load incidents.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const params = Object.fromEntries(searchParams.entries());
    fetchIncidents(params);

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        fetchIncidents(Object.fromEntries(searchParams.entries()), { silent: true });
      }
    }, 30000);
    return () => clearInterval(pollRef.current);
  }, [searchParams, fetchIncidents]);

  function setParam(key, value) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('page');
      return next;
    });
  }

  function setTab(tabKey) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (tabKey) next.set('tab', tabKey);
      else next.delete('tab');
      next.delete('page');
      return next;
    });
  }

  function setPage(p) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('page', p);
      return next;
    });
  }

  async function openPreview(displayId) {
    setPreview({ id: displayId, incident: null });
    setPreviewLoading(true);
    try {
      const res = await api.get(`/api/incidents/${displayId}/`);
      setPreview({ id: displayId, incident: res.data });
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  const { results, count, page, per_page, total_pages } = data;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Incidents</h1>
        <div className="flex items-center gap-3">
          {!loading && <span className="text-sm text-muted-foreground">{count} total</span>}
          <button
            onClick={() => setCreateOpen(true)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            New Incident
          </button>
        </div>
      </div>

      <CreateIncidentModal open={createOpen} onClose={() => setCreateOpen(false)} />

      <div className="flex gap-0 border-b border-border">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search…"
          value={searchParams.get('q') || ''}
          onChange={e => setParam('q', e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-48"
        />
        <select
          value={searchParams.get('severity') || ''}
          onChange={e => setParam('severity', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Severity filter"
        >
          <option value="">All severities</option>
          {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={searchParams.get('state') || ''}
          onChange={e => setParam('state', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="State filter"
        >
          <option value="">All states</option>
          {STATE_OPTIONS.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
        <select
          value={searchParams.get('tlp') || ''}
          onChange={e => setParam('tlp', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="TLP filter"
        >
          <option value="">All TLP</option>
          {TLP_OPTIONS.map(t => <option key={t} value={t}>TLP:{t.toUpperCase()}</option>)}
        </select>
        <select
          value={searchParams.get('created_within') || ''}
          onChange={e => setParam('created_within', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Created within filter"
        >
          <option value="">Any time</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Title</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">TLP</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">State</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">SLA</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Assignee</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">No incidents.</td>
              </tr>
            ) : (
              results.map(inc => (
                <tr
                  key={inc.id}
                  className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => openPreview(inc.display_id)}
                >
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">{inc.display_id}</td>
                  <td className="px-4 py-3 text-foreground max-w-xs truncate">{inc.title}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[inc.severity] ?? ''}`}>
                      {inc.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TLP_CLASSES[inc.tlp] ?? ''}`}>
                      TLP:{inc.tlp?.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${STATE_CLASSES[inc.state] ?? 'text-muted-foreground'}`}>
                      {inc.state?.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <SLAPill sla={inc.response_sla} label="Response SLA" />
                    <SLAPill sla={inc.resolve_sla} label="Resolve SLA" />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{inc.assignee_username || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                    {inc.created_at ? new Date(inc.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page} of {total_pages} ({count} total)
          </p>
          <div className="flex gap-1">
            {Array.from({ length: total_pages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                disabled={p === page}
                className={`rounded px-3 py-1 text-sm transition-colors ${
                  p === page
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border hover:bg-accent text-foreground'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}

      <SlideOver
        open={!!preview}
        onClose={() => setPreview(null)}
        title={preview?.incident?.display_id || 'Incident preview'}
        loading={previewLoading}
      >
        {preview?.incident && (
          <div className="px-6 py-4 space-y-4">
            <div>
              <h3 className="text-base font-semibold text-foreground">{preview.incident.title}</h3>
              {preview.incident.description && (
                <div className="prose prose-sm dark:prose-invert max-w-none mt-1">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{preview.incident.description}</ReactMarkdown>
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">State</p>
                <p className="text-foreground capitalize">{preview.incident.state?.replace('_', ' ')}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Severity</p>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[preview.incident.severity] ?? ''}`}>
                  {preview.incident.severity}
                </span>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Assignee</p>
                <p className="text-foreground">{preview.incident.assignee_username || '—'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Organisation</p>
                <p className="text-foreground">{preview.incident.org_slug}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Created</p>
                <p className="text-foreground text-xs">{preview.incident.created_at ? new Date(preview.incident.created_at).toLocaleString() : '—'}</p>
              </div>
            </div>
            <Link
              to={`/incidents/${preview.incident.display_id}`}
              className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Open incident →
            </Link>
          </div>
        )}
      </SlideOver>
    </div>
  );
}
