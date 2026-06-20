import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import { useOrganization } from '../context/OrgContext';
import SlideOver from '../components/SlideOver';
import BulkPromoteModal from '../components/BulkPromoteModal';
import CorrelationFromAlertsDrawer from '../components/CorrelationFromAlertsDrawer';
import RuleAuthorDrawer from '../components/RuleAuthorDrawer';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const STATE_CLASSES = {
  new:          'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  acknowledged: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  imported:     'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  ignored:      'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
};

const SOURCE_KIND_LABELS = {
  wazuh_event:   'Wazuh',
  vulnerability: 'CVE',
  agent_finding: 'Agent',
  api:           'API',
};

function formatDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function AlertDetailPanel({ alert, onClose, onStateChange, onDelete, orgSlug }) {
  const [relinkOpen, setRelinkOpen] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [incidentQuery, setIncidentQuery] = useState('');
  const [relinking, setRelinking] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleTransition = async (newState) => {
    setTransitioning(true);
    try {
      const resp = await api.patch(`/api/alerts/${alert.display_id}/`, { state: newState });
      onStateChange(resp.data);
    } catch {
      // ignore
    } finally {
      setTransitioning(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Permanently delete alert ${alert.display_id}? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.delete(`/api/alerts/${alert.display_id}/`);
      onDelete(alert.display_id);
      onClose();
    } catch {
      // ignore
    } finally {
      setDeleting(false);
    }
  };

  const openRelink = () => {
    setRelinkOpen(true);
    setIncidentQuery('');
    api.get('/api/incidents/', { params: { per_page: 50, state: 'new,triaged,in_progress,on_hold,pending_closure' } })
      .then(r => setIncidents(r.data.results ?? []))
      .catch(() => {});
  };

  const handleRelink = async (incidentDisplayId) => {
    setRelinking(true);
    try {
      const resp = await api.patch(`/api/alerts/${alert.display_id}/`, { incident: incidentDisplayId });
      onStateChange(resp.data);
      setRelinkOpen(false);
    } catch {
      // ignore
    } finally {
      setRelinking(false);
    }
  };

  const filteredIncidents = incidents.filter(i =>
    i.display_id.toLowerCase().includes(incidentQuery.toLowerCase()) ||
    i.title.toLowerCase().includes(incidentQuery.toLowerCase())
  );

  if (!alert) return null;

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-xs font-semibold text-muted-foreground">{alert.display_id}</span>
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[alert.severity] ?? ''}`}>
          {alert.severity}
        </span>
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATE_CLASSES[alert.state] ?? ''}`}>
          {alert.state}
        </span>
        <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-700 dark:text-slate-300">
          {SOURCE_KIND_LABELS[alert.source_kind] ?? alert.source_kind}
        </span>
      </div>

      <h3 className="text-sm font-medium text-foreground">{alert.title}</h3>

      <div className="text-xs text-muted-foreground">{formatDatetime(alert.created_at)}</div>

      {alert.incident_display_id && (
        <div className="text-sm">
          <span className="text-muted-foreground">Linked incident: </span>
          <Link
            to={`/incidents/${alert.incident_display_id}`}
            className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
            onClick={onClose}
          >
            {alert.incident_display_id}
          </Link>
        </div>
      )}

      {/* Source ref details */}
      {alert.source_ref && Object.keys(alert.source_ref).length > 0 && (
        <div className="rounded-md border border-border bg-muted/30 p-3">
          <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Source Details</p>
          <dl className="space-y-1">
            {Object.entries(alert.source_ref).map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <dt className="text-muted-foreground min-w-[100px] shrink-0">{k}</dt>
                <dd className="text-foreground font-mono break-all">
                  {v !== null && typeof v === 'object'
                    ? <pre className="whitespace-pre-wrap">{JSON.stringify(v, null, 2)}</pre>
                    : String(v)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-col gap-2 pt-2">
        {alert.state === 'new' && (
          <>
            <button
              onClick={() => handleTransition('acknowledged')}
              disabled={transitioning}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
            >
              Acknowledge
            </button>
            <button
              onClick={() => handleTransition('ignored')}
              disabled={transitioning}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
            >
              Ignore
            </button>
          </>
        )}
        {alert.state === 'acknowledged' && (
          <button
            onClick={() => handleTransition('ignored')}
            disabled={transitioning}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            Ignore
          </button>
        )}
        {alert.state === 'imported' && (
          <button
            onClick={openRelink}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
          >
            Re-link to incident…
          </button>
        )}
      </div>

      {/* Destructive actions */}
      <div className="pt-2 border-t border-border">
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="w-full rounded-md border border-red-200 dark:border-red-900/50 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
        >
          {deleting ? 'Deleting…' : 'Delete alert'}
        </button>
      </div>

      {/* Re-link incident picker */}
      {relinkOpen && (
        <div className="rounded-md border border-border bg-background p-3 flex flex-col gap-2">
          <p className="text-sm font-medium text-foreground">Select incident</p>
          <input
            type="search"
            placeholder="Search incidents…"
            value={incidentQuery}
            onChange={e => setIncidentQuery(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <div className="max-h-48 overflow-y-auto flex flex-col gap-1">
            {filteredIncidents.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No incidents found.</p>
            ) : filteredIncidents.map(inc => (
              <button
                key={inc.id}
                onClick={() => handleRelink(inc.display_id)}
                disabled={relinking}
                className="text-left rounded-md px-2 py-1.5 text-sm hover:bg-accent transition-colors disabled:opacity-50"
              >
                <span className="font-mono text-xs text-muted-foreground">{inc.display_id}</span>
                {' '}
                <span className="text-foreground">{inc.title}</span>
              </button>
            ))}
          </div>
          <button
            onClick={() => setRelinkOpen(false)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

function confidenceBadgeClass(confidence) {
  if (confidence >= 0.8) return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  if (confidence >= 0.6) return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400';
  return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
}

function SuggestionCard({ suggestion, acting, onAccept, onDismiss, onCodify, isStaff }) {
  return (
    <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-background p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Confidence</span>
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${confidenceBadgeClass(suggestion.confidence)}`}>
            {Math.round(suggestion.confidence * 100)}%
          </span>
        </div>
        <div className="flex gap-2 shrink-0 flex-wrap">
          <button
            onClick={() => onAccept(suggestion.id)}
            disabled={acting}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            Accept — Create Incident
          </button>
          <button
            onClick={() => onDismiss(suggestion.id)}
            disabled={acting}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            Dismiss
          </button>
          {isStaff && (
            <button
              onClick={() => onCodify(suggestion)}
              disabled={acting}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
            >
              Codify as rule
            </button>
          )}
        </div>
      </div>
      <p className="text-sm text-foreground">{suggestion.rationale}</p>
      {suggestion.proposed_alerts.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {suggestion.proposed_alerts.map(a => (
            <span
              key={a.id}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[a.severity] ?? 'bg-gray-100 text-gray-800'}`}
            >
              <span className="font-mono">{a.display_id}</span>
              <span className="opacity-70">{a.title}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function buildSuggestionSeed(suggestion) {
  const alertLines = suggestion.proposed_alerts
    .map(a => `- ${a.display_id}: ${a.title} (${a.severity})`)
    .join('\n');
  return `Codify the following correlated alerts into a detection rule.\n\nRationale: ${suggestion.rationale}\n\nAlerts:\n${alertLines}`;
}

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info'];
const STATE_OPTIONS = ['new', 'acknowledged', 'imported', 'ignored'];
const SOURCE_KIND_OPTIONS = ['wazuh_event', 'vulnerability', 'agent_finding', 'api'];

const EMPTY_DATA = { count: 0, page: 1, per_page: 25, total_pages: 1, results: [] };

function AlertsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();

  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const [suggestions, setSuggestions] = useState([]);
  const [acting, setActing] = useState(false);

  // Filters
  const [filterState, setFilterState] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterSourceKind, setFilterSourceKind] = useState('');
  const [showIgnored, setShowIgnored] = useState(false);
  const [filterLinked, setFilterLinked] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');

  // Selection
  const [selectedIds, setSelectedIds] = useState(new Set());

  // Detail panel
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);

  const [promoteModalOpen, setPromoteModalOpen] = useState(false);
  const [promoteOrgSlug, setPromoteOrgSlug] = useState(null);

  const [correlationDrawerOpen, setCorrelationDrawerOpen] = useState(false);
  const [codifySource, setCodifySource] = useState(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 25 };
      if (filterState) params.state = filterState;
      if (filterSeverity) params.severity = filterSeverity;
      if (filterSourceKind) params.source_kind = filterSourceKind;
      if (!showIgnored && !filterState) params.exclude_state = 'ignored';
      if (filterLinked === 'linked') params.has_incident = 'true';
      if (filterLinked === 'unlinked') params.has_incident = 'false';
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (search) params.search = search;

      const resp = await api.get('/api/alerts/', { params });
      setData(resp.data);
    } catch {
      setData(EMPTY_DATA);
    } finally {
      setLoading(false);
    }
  }, [page, filterState, filterSeverity, filterSourceKind, showIgnored, filterLinked, dateFrom, dateTo, search]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const fetchSuggestions = useCallback(async () => {
    if (!selectedOrg) return;
    try {
      const resp = await api.get('/api/correlations/suggestions/', { params: { org: selectedOrg.slug } });
      setSuggestions(resp.data);
    } catch {
      // ignore — suggestions are optional
    }
  }, [selectedOrg]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleAccept = async (id) => {
    setActing(true);
    try {
      const resp = await api.post(`/api/correlations/suggestions/${id}/accept/`);
      setSuggestions(prev => prev.filter(s => s.id !== id));
      if (resp.data.incident_display_id) {
        navigate(`/incidents/${resp.data.incident_display_id}`);
      }
    } catch {
      // ignore
    } finally {
      setActing(false);
    }
  };

  const handleDismiss = async (id) => {
    setActing(true);
    try {
      await api.post(`/api/correlations/suggestions/${id}/dismiss/`);
      setSuggestions(prev => prev.filter(s => s.id !== id));
    } catch {
      // ignore
    } finally {
      setActing(false);
    }
  };

  const openDetail = (alert) => {
    setSelectedAlert(alert);
    setPanelOpen(true);
  };

  const handleStateChange = (updatedAlert) => {
    setData(prev => ({
      ...prev,
      results: prev.results.map(a => a.display_id === updatedAlert.display_id ? updatedAlert : a),
    }));
    setSelectedAlert(updatedAlert);
  };

  const toggleSelect = (displayId) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(displayId)) next.delete(displayId);
      else next.add(displayId);
      return next;
    });
  };

  const allVisible = data.results.filter(a => a.state !== 'imported').map(a => a.display_id);
  const allSelected = allVisible.length > 0 && allVisible.every(id => selectedIds.has(id));

  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(allVisible));
    }
  };

  const handleBulkPromote = () => {
    const orgSlug = data.results.find(a => selectedIds.has(a.display_id))?.org_slug;
    if (!orgSlug) return;
    setPromoteOrgSlug(orgSlug);
    setPromoteModalOpen(true);
  };

  const handleAlertDeleted = (displayId) => {
    setData(prev => ({
      ...prev,
      count: prev.count - 1,
      results: prev.results.filter(a => a.display_id !== displayId),
    }));
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.delete(displayId);
      return next;
    });
  };

  const handleBulkDelete = async () => {
    const ids = [...selectedIds];
    if (!window.confirm(`Permanently delete ${ids.length} alert${ids.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
    for (const id of ids) {
      try {
        await api.delete(`/api/alerts/${id}/`);
        handleAlertDeleted(id);
      } catch {
        // continue deleting remaining
      }
    }
  };

  const handleQuickAction = async (e, alert, newState) => {
    e.stopPropagation();
    try {
      const resp = await api.patch(`/api/alerts/${alert.display_id}/`, { state: newState });
      handleStateChange(resp.data);
    } catch {
      // ignore
    }
  };

  const totalCount = data.count;
  const { results, total_pages } = data;

  const newCount = results.filter(a => a.state === 'new').length;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-foreground">Alert Inbox</h1>
          {newCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-400">
              {newCount} new
            </span>
          )}
        </div>
      </div>

      {/* Detection Suggestions */}
      {suggestions.length > 0 && (
        <div className="border-b border-border bg-blue-50/40 dark:bg-blue-950/20 px-6 py-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-400">
              AI
            </span>
            Detection Suggestions
            <span className="text-xs text-muted-foreground font-normal">({suggestions.length})</span>
          </h2>
          {suggestions.map(s => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              acting={acting}
              onAccept={handleAccept}
              onDismiss={handleDismiss}
              onCodify={setCodifySource}
              isStaff={user?.is_staff}
            />
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 px-6 py-3 border-b border-border bg-muted/20">
        <input
          type="search"
          placeholder="Search alerts…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground w-44 focus:outline-none focus:ring-1 focus:ring-ring"
        />

        <select
          value={filterSeverity}
          onChange={e => { setFilterSeverity(e.target.value); setPage(1); }}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
        >
          <option value="">All severities</option>
          {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={filterState}
          onChange={e => { setFilterState(e.target.value); setPage(1); }}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
        >
          <option value="">All states</option>
          {STATE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={filterSourceKind}
          onChange={e => { setFilterSourceKind(e.target.value); setPage(1); }}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
        >
          <option value="">All sources</option>
          {SOURCE_KIND_OPTIONS.map(s => <option key={s} value={s}>{SOURCE_KIND_LABELS[s] ?? s}</option>)}
        </select>

        <select
          value={filterLinked}
          onChange={e => { setFilterLinked(e.target.value); setPage(1); }}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
        >
          <option value="">All incidents</option>
          <option value="linked">Linked to incident</option>
          <option value="unlinked">Not linked</option>
        </select>

        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span>From</span>
          <input
            type="date"
            value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(1); }}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span>To</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(1); }}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={showIgnored}
            onChange={e => { setShowIgnored(e.target.checked); setPage(1); }}
            className="rounded border-border"
          />
          Show ignored
        </label>
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto">
        {/* Mobile card list */}
        <div className="sm:hidden space-y-2 p-3">
          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
          ) : results.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {filterState || filterSeverity || filterSourceKind || filterLinked || dateFrom || dateTo || search
                ? 'No alerts match the current filters.'
                : 'No alerts.'}
            </p>
          ) : results.map(alert => (
            <div
              key={alert.display_id}
              className="rounded-lg border border-border bg-card px-4 py-3 space-y-2 cursor-pointer hover:bg-accent/50 transition-colors"
              onClick={() => openDetail(alert)}
            >
              <div className="flex items-center gap-2">
                {alert.state !== 'imported' && (
                  <span onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(alert.display_id)}
                      onChange={() => toggleSelect(alert.display_id)}
                      className="rounded border-border"
                      aria-label={`Select ${alert.display_id}`}
                    />
                  </span>
                )}
                <span className="font-mono text-xs font-medium text-foreground">{alert.display_id}</span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[alert.severity] ?? ''}`}>
                  {alert.severity}
                </span>
                <span className={`ml-auto inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATE_CLASSES[alert.state] ?? ''}`}>
                  {alert.state}
                </span>
              </div>
              <p className="text-sm font-medium text-foreground leading-snug">{alert.title}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 font-medium text-slate-700 dark:text-slate-300">
                  {SOURCE_KIND_LABELS[alert.source_kind] ?? alert.source_kind}
                </span>
                {alert.incident_display_id && (
                  <Link
                    to={`/incidents/${alert.incident_display_id}`}
                    className="font-mono text-blue-600 hover:underline dark:text-blue-400"
                    onClick={e => e.stopPropagation()}
                  >
                    {alert.incident_display_id}
                  </Link>
                )}
                <span className="ml-auto">{formatDatetime(alert.created_at)}</span>
              </div>
              {alert.state === 'new' && (
                <div className="flex gap-2 pt-1" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={e => handleQuickAction(e, alert, 'acknowledged')}
                    className="rounded px-2 py-1 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50 transition-colors"
                  >
                    Ack
                  </button>
                  <button
                    onClick={e => handleQuickAction(e, alert, 'ignored')}
                    className="rounded px-2 py-1 text-xs bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
                  >
                    Ignore
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Desktop table */}
        <table className="hidden sm:table w-full text-sm">
          <thead className="sticky top-0 bg-muted/50 backdrop-blur border-b border-border">
            <tr>
              <th className="px-4 py-2 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="rounded border-border"
                  aria-label="Select all"
                />
              </th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">ID</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Title</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Severity</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">State</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Source</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Incident</th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Created</th>
              <th className="px-4 py-2 w-24" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-sm text-muted-foreground">
                  {filterState || filterSeverity || filterSourceKind || filterLinked || dateFrom || dateTo || search
                    ? 'No alerts match the current filters.'
                    : showIgnored
                      ? 'No alerts.'
                      : 'No alerts. Ignored alerts are hidden — toggle above to show them.'}
                </td>
              </tr>
            ) : results.map(alert => (
              <tr
                key={alert.display_id}
                className="hover:bg-muted/30 cursor-pointer transition-colors group"
                onClick={() => openDetail(alert)}
              >
                <td className="px-4 py-3 w-8" onClick={e => e.stopPropagation()}>
                  {alert.state !== 'imported' && (
                    <input
                      type="checkbox"
                      checked={selectedIds.has(alert.display_id)}
                      onChange={() => toggleSelect(alert.display_id)}
                      className="rounded border-border"
                      aria-label={`Select ${alert.display_id}`}
                    />
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs font-medium text-foreground whitespace-nowrap">
                  {alert.display_id}
                </td>
                <td className="px-4 py-3 text-foreground max-w-xs truncate">{alert.title}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[alert.severity] ?? ''}`}>
                    {alert.severity}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATE_CLASSES[alert.state] ?? ''}`}>
                    {alert.state}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-700 dark:text-slate-300">
                    {SOURCE_KIND_LABELS[alert.source_kind] ?? alert.source_kind}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {alert.incident_display_id ? (
                    <Link
                      to={`/incidents/${alert.incident_display_id}`}
                      className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
                      onClick={e => e.stopPropagation()}
                    >
                      {alert.incident_display_id}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground text-xs">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                  {formatDatetime(alert.created_at)}
                </td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  {alert.state === 'new' && (
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={e => handleQuickAction(e, alert, 'acknowledged')}
                        className="rounded px-2 py-1 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50 transition-colors"
                        title="Acknowledge"
                      >
                        Ack
                      </button>
                      <button
                        onClick={e => handleQuickAction(e, alert, 'ignored')}
                        className="rounded px-2 py-1 text-xs bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
                        title="Ignore"
                      >
                        Ignore
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total_pages > 1 && (
        <div className="flex items-center justify-between px-6 py-3 border-t border-border text-sm text-muted-foreground">
          <span>{totalCount} alerts</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-border px-3 py-1 hover:bg-accent transition-colors disabled:opacity-50"
            >
              Previous
            </button>
            <span className="px-2 py-1">Page {page} of {total_pages}</span>
            <button
              onClick={() => setPage(p => Math.min(total_pages, p + 1))}
              disabled={page === total_pages}
              className="rounded-md border border-border px-3 py-1 hover:bg-accent transition-colors disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Floating bulk action toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">
            {selectedIds.size} selected
          </span>
          <button
            onClick={handleBulkPromote}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            {`Create incident (${selectedIds.size})`}
          </button>
          {user?.is_staff && (
            <button
              onClick={() => setCorrelationDrawerOpen(true)}
              className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
            >
              Create correlation rule
            </button>
          )}
          <button
            onClick={handleBulkDelete}
            className="rounded-lg px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            Delete selected
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      )}

      <BulkPromoteModal
        open={promoteModalOpen}
        alertIds={[...selectedIds].filter(id => {
          const a = data.results.find(r => r.display_id === id);
          return a && a.state !== 'imported' && a.state !== 'ignored';
        })}
        orgSlug={promoteOrgSlug}
        onClose={() => setPromoteModalOpen(false)}
        onSuccess={(incidentId) => {
          setSelectedIds(new Set());
          setPromoteModalOpen(false);
          navigate(`/incidents/${incidentId}`);
        }}
      />

      {/* Correlation rule creation from selected alerts */}
      {correlationDrawerOpen && (
        <CorrelationFromAlertsDrawer
          alerts={data.results.filter(a => selectedIds.has(a.display_id))}
          onClose={() => setCorrelationDrawerOpen(false)}
          onCreated={() => {
            setCorrelationDrawerOpen(false);
            setSelectedIds(new Set());
          }}
        />
      )}

      {/* Codify suggestion as a correlation rule */}
      {codifySource && (
        <RuleAuthorDrawer
          initialScope={selectedOrg?.slug}
          initialMessage={buildSuggestionSeed(codifySource)}
          onClose={() => setCodifySource(null)}
          onSaved={() => setCodifySource(null)}
        />
      )}

      {/* Detail slide-over */}
      <SlideOver
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title={selectedAlert?.display_id ?? 'Alert'}
      >
        {selectedAlert && (
          <AlertDetailPanel
            alert={selectedAlert}
            onClose={() => setPanelOpen(false)}
            onStateChange={handleStateChange}
            onDelete={handleAlertDeleted}
            orgSlug={selectedAlert.org_slug}
          />
        )}
      </SlideOver>
    </div>
  );
}

export default AlertsPage;
