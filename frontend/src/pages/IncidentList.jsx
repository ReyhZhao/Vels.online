import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import SLAPill from '../components/SLAPill';
import CreateIncidentModal from '../components/CreateIncidentModal';
import { OnCallWidgetCompact } from '../components/OnCallWidget';

// Keys that are persisted as user preferences (excludes transient keys like page, q)
const PREF_KEYS = ['tab', 'severity', 'state', 'tlp', 'created_within', 'sort', 'order'];

function getPrefsStorageKey(userId) {
  return `incident_list_prefs_${userId ?? 'anon'}`;
}

function loadPrefs(userId) {
  try {
    const raw = localStorage.getItem(getPrefsStorageKey(userId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function savePrefs(userId, searchParams) {
  try {
    const prefs = {};
    PREF_KEYS.forEach(k => {
      const v = searchParams.get(k);
      if (v) prefs[k] = v;
    });
    localStorage.setItem(getPrefsStorageKey(userId), JSON.stringify(prefs));
  } catch {
    // Ignore storage errors (private mode, quota exceeded, etc.)
  }
}

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const STATE_CLASSES = {
  new:          'text-blue-600 dark:text-blue-400',
  triaged:      'text-purple-600 dark:text-purple-400',
  in_progress:  'text-yellow-600 dark:text-yellow-400',
  on_hold:      'text-orange-600 dark:text-orange-400',
  needs_tuning: 'text-amber-600 dark:text-amber-400',
  pending_closure: 'text-teal-600 dark:text-teal-400',
  resolved:     'text-green-600 dark:text-green-400',
  closed:       'text-muted-foreground',
};

const TABS = [
  { key: 'my_queue',   label: 'My Queue' },
  { key: 'unassigned', label: 'Unassigned' },
  { key: '',           label: 'All' },
];

// The complete set of real incident states, in workflow order. Keep in sync
// with STATE_CLASSES / the backend Incident.STATE_* choices — notably this
// includes `pending_closure` and `closed`.
const STATE_OPTIONS      = ['new', 'triaged', 'in_progress', 'on_hold', 'needs_tuning', 'pending_closure', 'resolved', 'closed'];
// Default state selection: every state except `closed`. Mirrors the backend's
// implicit "exclude closed when no explicit state" behaviour, so when the
// selection equals this we omit the `state` param entirely (see setStates).
const DEFAULT_STATES     = STATE_OPTIONS.filter(s => s !== 'closed');
const SEVERITY_OPTIONS   = ['critical', 'high', 'medium', 'low', 'info'];
const TLP_OPTIONS        = ['white', 'green', 'amber', 'red'];

const prettyState = s => s.replace(/_/g, ' ');

function sameStateSet(a, b) {
  if (a.length !== b.length) return false;
  const setB = new Set(b);
  return a.every(s => setB.has(s));
}

const EMPTY_DATA = { count: 0, page: 1, per_page: 25, total_pages: 1, results: [] };

function formatDatetime(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  return d.toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const SORT_COLUMNS = {
  title:      { label: 'Title',    defaultOrder: 'asc'  },
  severity:   { label: 'Severity', defaultOrder: 'desc' },
  state:      { label: 'State',    defaultOrder: 'asc'  },
  assignee:   { label: 'Assignee', defaultOrder: 'asc'  },
  created_at: { label: 'Created',  defaultOrder: 'asc'  },
};

const CLOSURE_REASONS = [
  { value: 'resolved',       label: 'Resolved' },
  { value: 'false_positive', label: 'False Positive' },
  { value: 'no_impact',      label: 'No Impact' },
  { value: 'duplicate',      label: 'Duplicate' },
  { value: 'informational',  label: 'Informational' },
  { value: 'accepted_risk',  label: 'Accepted Risk' },
];

function CanonicalIncidentCombobox({ incidents, loading, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef(null);

  const selected = incidents.find(i => String(i.id) === String(value));

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const filtered = incidents.filter(i => {
    const q = search.toLowerCase();
    return (
      i.display_id?.toLowerCase().includes(q) ||
      i.title?.toLowerCase().includes(q)
    );
  });

  function select(incident) {
    onChange(String(incident.id));
    setSearch('');
    setOpen(false);
  }

  function handleInputChange(e) {
    setSearch(e.target.value);
    onChange('');
    if (!open) setOpen(true);
  }

  function handleInputFocus() {
    setOpen(true);
  }

  const displayValue = open ? search : (selected ? `${selected.display_id} — ${selected.title}` : '');

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-label="Canonical incident"
        id="bulk-duplicate-of"
        value={displayValue}
        onChange={handleInputChange}
        onFocus={handleInputFocus}
        disabled={loading}
        placeholder={loading ? 'Loading…' : 'Search incidents…'}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        autoComplete="off"
      />
      {open && !loading && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-card shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">No incidents found</li>
          ) : (
            filtered.map(i => (
              <li
                key={i.id}
                role="option"
                aria-selected={String(i.id) === String(value)}
                onMouseDown={e => { e.preventDefault(); select(i); }}
                className={`cursor-pointer px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground ${String(i.id) === String(value) ? 'bg-accent/50' : ''}`}
              >
                <span className="font-medium">{i.display_id}</span>
                <span className="text-muted-foreground"> — {i.title}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function BulkCloseDialog({ onConfirm, onCancel, loading, excludeIds }) {
  const [reason, setReason] = useState('');
  const [duplicateOf, setDuplicateOf] = useState('');
  const [canonicalIncidents, setCanonicalIncidents] = useState([]);
  const [canonicalLoading, setCanonicalLoading] = useState(false);

  useEffect(() => {
    if (reason !== 'duplicate') { setDuplicateOf(''); return; }
    setCanonicalLoading(true);
    api.get('/api/incidents/', { params: { page_size: 500, exclude_states: 'closed' } })
      .then(res => {
        const items = (res.data.results ?? res.data);
        setCanonicalIncidents(items.filter(i => !excludeIds.has(i.id)));
      })
      .catch(() => setCanonicalIncidents([]))
      .finally(() => setCanonicalLoading(false));
  }, [reason]); // eslint-disable-line react-hooks/exhaustive-deps

  const canSubmit = reason && (reason !== 'duplicate' || duplicateOf);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Bulk close incidents</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="bulk-closure-reason">
            Closure reason
          </label>
          <select
            id="bulk-closure-reason"
            value={reason}
            onChange={e => setReason(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a reason…</option>
            {CLOSURE_REASONS.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        {reason === 'duplicate' && (
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-foreground" htmlFor="bulk-duplicate-of">
              Canonical incident <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-muted-foreground">
              All selected incidents will be linked to this incident as duplicates. It stays open.
            </p>
            <CanonicalIncidentCombobox
              incidents={canonicalIncidents}
              loading={canonicalLoading}
              value={duplicateOf}
              onChange={setDuplicateOf}
            />
          </div>
        )}

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => canSubmit && onConfirm(reason, duplicateOf ? Number(duplicateOf) : null)}
            disabled={!canSubmit || loading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Closing…' : 'Close incidents'}
          </button>
        </div>
      </div>
    </div>
  );
}

function BulkReassignDialog({ staffUsers, onConfirm, onCancel, loading }) {
  const [assigneeId, setAssigneeId] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Bulk reassign incidents</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="bulk-assignee">
            Assign to
          </label>
          <select
            id="bulk-assignee"
            value={assigneeId}
            onChange={e => setAssigneeId(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select…</option>
            <option value="null">Unassigned</option>
            {staffUsers.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => assigneeId !== '' && onConfirm(assigneeId === 'null' ? null : Number(assigneeId))}
            disabled={assigneeId === '' || loading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Reassigning…' : 'Confirm reassign'}
          </button>
        </div>
      </div>
    </div>
  );
}

function StateMultiSelect({ selected, onToggle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const selectedSet = new Set(selected);

  let summary;
  if (selected.length === 0) summary = 'No states';
  else if (selected.length === STATE_OPTIONS.length) summary = 'All states';
  else if (sameStateSet(selected, DEFAULT_STATES)) summary = 'All except closed';
  else if (selected.length <= 2) summary = selected.map(prettyState).join(', ');
  else summary = `${selected.length} states`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="State filter"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <span>{summary}</span>
        <span aria-hidden="true" className="text-muted-foreground">▾</span>
      </button>
      {open && (
        <div
          role="group"
          aria-label="Incident states"
          className="absolute z-50 mt-1 min-w-[12rem] rounded-md border border-border bg-card py-1 shadow-lg"
        >
          {STATE_OPTIONS.map(s => {
            const checked = selectedSet.has(s);
            // Never let the user clear the last remaining state — an empty
            // selection has no sensible meaning, so keep at least one checked.
            const lockLast = checked && selected.length === 1;
            return (
              <label
                key={s}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm capitalize hover:bg-accent ${lockLast ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
              >
                <input
                  type="checkbox"
                  aria-label={s}
                  checked={checked}
                  disabled={lockLast}
                  onChange={() => onToggle(s)}
                  className="rounded border-border"
                />
                <span className={STATE_CLASSES[s] ?? 'text-foreground'}>{prettyState(s)}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function IncidentList() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData]         = useState(EMPTY_DATA);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectAllPages, setSelectAllPages] = useState(false);
  const [bulkAction, setBulkAction]   = useState(null);
  const [staffUsers, setStaffUsers]   = useState([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkError, setBulkError]     = useState(null);
  const [bulkResult, setBulkResult]   = useState(null);
  const pollRef = useRef(null);

  const activeTab = searchParams.get('tab') ?? '';

  // Track whether initialization (pref restore) is done so we know when to start saving
  const isFirstSaveRef = useRef(true);

  // On mount: restore saved preferences if the URL has no filter/sort params
  useEffect(() => {
    const hasParams = PREF_KEYS.some(k => searchParams.has(k));
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (!hasParams) {
        const saved = loadPrefs(user?.id);
        if (saved) {
          Object.entries(saved).forEach(([k, v]) => next.set(k, v));
        }
      }
      if (!next.has('tab')) next.set('tab', 'my_queue');
      return next;
    }, { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Save preferences whenever the user changes filters/sort (skip the very first render)
  useEffect(() => {
    if (isFirstSaveRef.current) {
      isFirstSaveRef.current = false;
      return;
    }
    savePrefs(user?.id, searchParams);
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

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
    setSelectAllPages(false);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('page');
      return next;
    });
  }

  // Multi-value state filter. When the URL has no `state` param we show the
  // default (every state except closed); otherwise we reflect the param.
  const stateParam = searchParams.get('state');
  const selectedStates = stateParam
    ? stateParam.split(',').map(s => s.trim()).filter(Boolean)
    : DEFAULT_STATES;

  function setStates(nextStates) {
    setSelectAllPages(false);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      // The default (all-except-closed) is expressed by omitting the param, so
      // the backend's built-in closed-exclusion applies and the URL stays clean
      // (and future non-closed states are picked up automatically).
      if (sameStateSet(nextStates, DEFAULT_STATES)) next.delete('state');
      else next.set('state', nextStates.join(','));
      next.delete('page');
      return next;
    });
  }

  function toggleState(stateValue) {
    const current = new Set(selectedStates);
    if (current.has(stateValue)) {
      if (current.size === 1) return; // keep at least one state selected
      current.delete(stateValue);
    } else {
      current.add(stateValue);
    }
    setStates(STATE_OPTIONS.filter(s => current.has(s)));
  }

  function setTab(tabKey) {
    setSelectAllPages(false);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (tabKey) next.set('tab', tabKey);
      else next.delete('tab');
      next.delete('page');
      return next;
    });
  }

  function setPage(p) {
    setSelectAllPages(false);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('page', p);
      return next;
    });
  }

  const sortKey = searchParams.get('sort') || '';
  const sortOrder = searchParams.get('order') || 'asc';

  function setSort(field) {
    setSelectAllPages(false);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (sortKey === field) {
        next.set('order', sortOrder === 'asc' ? 'desc' : 'asc');
      } else {
        next.set('sort', field);
        next.set('order', SORT_COLUMNS[field]?.defaultOrder ?? 'asc');
      }
      next.delete('page');
      return next;
    });
  }

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const visibleIds = data.results.map(inc => inc.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
    if (allSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.add(id));
        return next;
      });
    }
  }

  async function openBulkReassign() {
    if (staffUsers.length === 0) {
      try {
        const res = await api.get('/api/incidents/staff-users/');
        setStaffUsers(res.data);
      } catch {
        setBulkError('Failed to load staff users.');
        return;
      }
    }
    setBulkError(null);
    setBulkAction('reassign');
  }

  async function executeBulkAction(action, extra) {
    setBulkLoading(true);
    setBulkError(null);
    setBulkResult(null);
    try {
      const payload = selectAllPages
        ? { action, select_all: true, filters: Object.fromEntries(searchParams), ...extra }
        : { action, ids: [...selectedIds], ...extra };
      const res = await api.post('/api/incidents/bulk/', payload);
      const { succeeded, failed } = res.data;
      setBulkResult({ succeeded: succeeded.length, failed });
      setSelectedIds(new Set());
      setSelectAllPages(false);
      setBulkAction(null);
      fetchIncidents(Object.fromEntries(searchParams.entries()), { silent: true });
    } catch (err) {
      setBulkError(err.response?.data?.detail || 'Bulk action failed.');
    } finally {
      setBulkLoading(false);
    }
  }

  const { results, count, page, per_page, total_pages } = data;
  const visibleIds = results.map(inc => inc.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
  const someVisibleSelected = visibleIds.some(id => selectedIds.has(id));
  const colSpan = user?.is_staff ? 9 : 8;

  function getPaginationPages(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [1];
    if (current - 1 > 2) pages.push('…');
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i);
    if (current + 1 < total - 1) pages.push('…');
    pages.push(total);
    return pages;
  }

  return (
    <div className="space-y-4 p-6">
      {bulkAction === 'close' && (
        <BulkCloseDialog
          loading={bulkLoading}
          excludeIds={selectedIds}
          onConfirm={(reason, duplicateOfId) => executeBulkAction('close', {
            closure_reason: reason,
            ...(reason === 'duplicate' && duplicateOfId ? { duplicate_of: duplicateOfId } : {}),
          })}
          onCancel={() => { setBulkAction(null); setBulkError(null); }}
        />
      )}

      {bulkAction === 'reassign' && (
        <BulkReassignDialog
          staffUsers={staffUsers}
          loading={bulkLoading}
          onConfirm={assigneeId => executeBulkAction('reassign', { assignee_id: assigneeId })}
          onCancel={() => { setBulkAction(null); setBulkError(null); }}
        />
      )}

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

      {user?.is_staff && (
        <div className="flex items-center gap-2">
          <OnCallWidgetCompact />
        </div>
      )}

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
        <StateMultiSelect selected={selectedStates} onToggle={toggleState} />
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

      {user?.is_staff && selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md border border-border bg-card px-4 py-2">
          <span className="text-sm font-medium text-foreground">{selectedIds.size} selected</span>
          <div className="flex gap-2 ml-2">
            <button
              onClick={() => { setBulkError(null); setBulkResult(null); setBulkAction('close'); }}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 transition-colors"
            >
              Close
            </button>
            <button
              onClick={() => { setBulkError(null); setBulkResult(null); openBulkReassign(); }}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors"
            >
              Reassign
            </button>
          </div>
          {bulkError && <span className="text-sm text-red-600 ml-2">{bulkError}</span>}
          {bulkResult && (
            <span className="text-sm text-foreground ml-2">
              {bulkResult.succeeded} succeeded
              {bulkResult.failed.length > 0 && (
                <span className="ml-1 text-red-600">
                  , {bulkResult.failed.length} failed:
                  <ul className="mt-1 list-none space-y-0.5">
                    {bulkResult.failed.map(f => (
                      <li key={f.id} className="text-xs">ID {f.id}: {f.error}</li>
                    ))}
                  </ul>
                </span>
              )}
            </span>
          )}
          <button
            onClick={() => { setSelectedIds(new Set()); setSelectAllPages(false); setBulkResult(null); setBulkError(null); }}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        </div>
      )}

      {user?.is_staff && allVisibleSelected && total_pages > 1 && !selectAllPages && (
        <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 px-4 py-2 text-sm text-blue-800 dark:text-blue-300">
          All <strong>{per_page}</strong> incidents on this page are selected.{' '}
          <button
            onClick={() => setSelectAllPages(true)}
            className="underline font-medium hover:text-blue-600 dark:hover:text-blue-200"
          >
            Select all {count} incidents matching these filters
          </button>
        </div>
      )}
      {user?.is_staff && selectAllPages && (
        <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 px-4 py-2 text-sm text-blue-800 dark:text-blue-300">
          All <strong>{count}</strong> incidents are selected.{' '}
          <button
            onClick={() => { setSelectAllPages(false); setSelectedIds(new Set()); }}
            className="underline font-medium hover:text-blue-600 dark:hover:text-blue-200"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : results.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No incidents.</p>
        ) : results.map(inc => (
          <div
            key={inc.id}
            className="rounded-lg border border-border bg-card px-4 py-3 space-y-1 cursor-pointer hover:bg-accent/50 transition-colors"
            onClick={() => navigate(`/incidents/${inc.display_id}`)}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs font-medium text-foreground">{inc.display_id}</span>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[inc.severity] ?? ''}`}>
                {inc.severity}
              </span>
            </div>
            <p className="text-sm font-medium text-foreground leading-snug">{inc.title}</p>
            <div className="flex items-center gap-3 text-xs">
              <span className={`font-medium ${STATE_CLASSES[inc.state] ?? 'text-muted-foreground'}`}>
                {inc.state?.replace('_', ' ')}
              </span>
              <span className="text-muted-foreground">{inc.assignee_username || 'Unassigned'}</span>
              {(inc.org_name || inc.org_slug) && (
                <span className="text-muted-foreground">{inc.org_name || inc.org_slug}</span>
              )}
              <span className="text-muted-foreground ml-auto">
                {formatDatetime(inc.created_at)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              {user?.is_staff && (
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allVisibleSelected}
                    ref={el => { if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected; }}
                    onChange={toggleSelectAll}
                    className="rounded border-border"
                  />
                </th>
              )}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">ID</th>
              {['title', 'severity', 'state'].map(field => (
                <th key={field} className="px-4 py-3 text-left font-medium text-muted-foreground">
                  <button
                    onClick={() => setSort(field)}
                    className="flex items-center gap-1 hover:text-foreground transition-colors"
                    aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
                  >
                    {SORT_COLUMNS[field].label}
                    {sortKey === field && (
                      <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>
                    )}
                  </button>
                </th>
              ))}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Org</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">SLA</th>
              {['assignee', 'created_at'].map(field => (
                <th key={field} className="px-4 py-3 text-left font-medium text-muted-foreground">
                  <button
                    onClick={() => setSort(field)}
                    className="flex items-center gap-1 hover:text-foreground transition-colors"
                    aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
                  >
                    {SORT_COLUMNS[field].label}
                    {sortKey === field && (
                      <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={colSpan} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-4 py-8 text-center text-muted-foreground">No incidents.</td>
              </tr>
            ) : (
              results.map(inc => (
                <tr
                  key={inc.id}
                  className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => navigate(`/incidents/${inc.display_id}`)}
                >
                  {user?.is_staff && (
                    <td className="px-4 py-3 w-8" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${inc.display_id}`}
                        checked={selectedIds.has(inc.id)}
                        onChange={() => toggleSelect(inc.id)}
                        className="rounded border-border"
                      />
                    </td>
                  )}
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">
                    <div className="flex items-center gap-1.5">
                      {inc.display_id}
                      {inc.linked_alert_count > 0 && (
                        <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/30 px-1.5 py-0.5 text-xs font-semibold text-blue-700 dark:text-blue-400" title={`${inc.linked_alert_count} linked alert${inc.linked_alert_count === 1 ? '' : 's'}`}>
                          {inc.linked_alert_count}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-foreground max-w-xs truncate">{inc.title}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[inc.severity] ?? ''}`}>
                      {inc.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium ${STATE_CLASSES[inc.state] ?? 'text-muted-foreground'}`}>
                      {inc.state?.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{inc.org_name || inc.org_slug || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      <SLAPill sla={inc.response_sla} label="Response SLA" compact />
                      <SLAPill sla={inc.resolve_sla} label="Resolve SLA" compact />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{inc.assignee_username || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                    {formatDatetime(inc.created_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>{/* end desktop table */}

      {total_pages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Page {page} of {total_pages} ({count} total)
          </p>
          <div className="flex flex-wrap gap-1">
            {getPaginationPages(page, total_pages).map((p, i) =>
              p === '…' ? (
                <span key={`ellipsis-${i}`} className="px-2 py-1 text-sm text-muted-foreground select-none">…</span>
              ) : (
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
              )
            )}
          </div>
        </div>
      )}

    </div>
  );
}
