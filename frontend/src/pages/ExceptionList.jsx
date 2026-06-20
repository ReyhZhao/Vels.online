import { useState, useEffect, Fragment } from 'react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import EditExceptionModal from '../components/EditExceptionModal';

const STATUS_OPTIONS = ['pending', 'applied', 'disabled'];

const STATUS_CLASSES = {
  pending:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  applied:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  disabled: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const SCOPE_CLASSES = {
  org:    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  global: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
};

export default function ExceptionList() {
  const { user } = useAuth();
  const isStaff = user?.is_staff;

  const [rules, setRules]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [statusFilter, setStatus] = useState('');
  const [orgFilter, setOrg]       = useState('');
  const [search, setSearch]       = useState('');
  const [editRule, setEditRule]   = useState(null);
  const [actionErrors, setActionErrors] = useState({});
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [sortKey, setSortKey] = useState('');
  const [sortOrder, setSortOrder] = useState('asc');

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  }

  const filteredRules = search.trim()
    ? rules.filter(r => {
        const q = search.toLowerCase();
        return (
          String(r.wazuh_rule_id ?? '').toLowerCase().includes(q) ||
          (r.description || '').toLowerCase().includes(q) ||
          (r.org_slug || '').toLowerCase().includes(q)
        );
      })
    : rules;

  const sortedRules = sortKey
    ? [...filteredRules].sort((a, b) => {
        const dir = sortOrder === 'asc' ? 1 : -1;
        if (sortKey === 'wazuh_rule_id') {
          const an = Number(a.wazuh_rule_id), bn = Number(b.wazuh_rule_id);
          if (!Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * dir;
        }
        const av = (a[sortKey] ?? '').toString().toLowerCase();
        const bv = (b[sortKey] ?? '').toString().toLowerCase();
        return av.localeCompare(bv) * dir;
      })
    : filteredRules;

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const ids = sortedRules.map(r => r.id);
    const allSelected = ids.length > 0 && ids.every(id => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(ids));
  }

  async function handleBulkApprove() {
    const targets = sortedRules.filter(r => selectedIds.has(r.id) && r.status === 'pending');
    for (const rule of targets) {
      await handleApprove(rule);
    }
    setSelectedIds(new Set());
  }

  async function handleBulkDisable() {
    const targets = sortedRules.filter(r => selectedIds.has(r.id) && r.status === 'applied');
    for (const rule of targets) {
      await handleDisable(rule);
    }
    setSelectedIds(new Set());
  }

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (orgFilter)    params.organisation = orgFilter;
    api.get('/api/exceptions/', { params })
      .then(res => setRules(res.data))
      .catch(err => setError(err.response?.data?.detail || 'Failed to load exception rules.'))
      .finally(() => setLoading(false));
  }, [statusFilter, orgFilter]);

  function updateRule(updated) {
    setRules(rs => rs.map(r => r.id === updated.id ? updated : r));
  }

  function clearActionError(id) {
    setActionErrors(e => { const n = { ...e }; delete n[id]; return n; });
  }

  async function handleApprove(rule) {
    clearActionError(rule.id);
    try {
      const res = await api.post(`/api/exceptions/${rule.id}/approve/`);
      updateRule(res.data);
    } catch (err) {
      setActionErrors(e => ({ ...e, [rule.id]: err.response?.data?.detail || 'Approve failed.' }));
    }
  }

  async function handleDisable(rule) {
    clearActionError(rule.id);
    try {
      const res = await api.post(`/api/exceptions/${rule.id}/disable/`);
      updateRule(res.data);
    } catch (err) {
      setActionErrors(e => ({ ...e, [rule.id]: err.response?.data?.detail || 'Disable failed.' }));
    }
  }

  const colCount = isStaff ? 8 : 5;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Exception Rules</h1>
        {!loading && <span className="text-sm text-muted-foreground">{rules.length} total</span>}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search exception rules"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-48"
        />
        <select
          value={statusFilter}
          onChange={e => setStatus(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        {isStaff && (
          <input
            type="text"
            placeholder="Filter by org slug…"
            value={orgFilter}
            onChange={e => setOrg(e.target.value)}
            aria-label="Organisation filter"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-48"
          />
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : sortedRules.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No exception rules.</p>
        ) : sortedRules.map(rule => (
          <div key={rule.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                {isStaff && (
                  <input
                    type="checkbox"
                    checked={selectedIds.has(rule.id)}
                    onChange={() => toggleSelect(rule.id)}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    aria-label={`Select rule ${rule.wazuh_rule_id ?? rule.id}`}
                  />
                )}
                <span className="font-mono text-xs font-medium text-foreground">{rule.wazuh_rule_id ?? '—'}</span>
              </span>
              <div className="flex items-center gap-1.5">
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SCOPE_CLASSES[rule.scope] ?? ''}`}>
                  {rule.scope}
                </span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[rule.status] ?? ''}`}>
                  {rule.status}
                </span>
              </div>
            </div>
            <p className="text-sm text-foreground leading-snug">{rule.description || '—'}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {isStaff && rule.org_slug && <span>{rule.org_slug}</span>}
              {rule.incident_display_id && (
                <a href={`/incidents/${rule.incident_display_id}`} className="text-primary hover:underline">
                  {rule.incident_display_id}
                </a>
              )}
            </div>
            {isStaff && (
              <div className="flex gap-2 pt-1">
                {rule.status === 'pending' && (
                  <button
                    onClick={() => handleApprove(rule)}
                    className="rounded px-2 py-1 text-xs font-medium bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400"
                  >
                    Approve
                  </button>
                )}
                <button
                  onClick={() => setEditRule(rule)}
                  className="rounded px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400"
                >
                  Edit
                </button>
                {rule.status === 'applied' && (
                  <button
                    onClick={() => handleDisable(rule)}
                    className="rounded px-2 py-1 text-xs font-medium bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400"
                  >
                    Disable
                  </button>
                )}
                {actionErrors[rule.id] && (
                  <span className="text-xs text-red-600">{actionErrors[rule.id]}</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              {isStaff && (
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={sortedRules.length > 0 && sortedRules.every(r => selectedIds.has(r.id))}
                    onChange={toggleSelectAll}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    aria-label="Select all"
                  />
                </th>
              )}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('wazuh_rule_id')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Rule ID">
                  Rule ID
                  {sortKey === 'wazuh_rule_id' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('scope')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Scope">
                  Scope
                  {sortKey === 'scope' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('status')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Status">
                  Status
                  {sortKey === 'status' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              {isStaff && (
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  <button onClick={() => setSort('org_slug')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Organisation">
                    Organisation
                    {sortKey === 'org_slug' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                  </button>
                </th>
              )}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Incident</th>
              {isStaff && <th className="px-4 py-3 text-left font-medium text-muted-foreground">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={colCount} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : sortedRules.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="px-4 py-8 text-center text-muted-foreground">
                  No exception rules.
                </td>
              </tr>
            ) : (
              sortedRules.map(rule => (
                <Fragment key={rule.id}>
                  <tr className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                    {isStaff && (
                      <td className="px-4 py-3 w-8">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(rule.id)}
                          onChange={() => toggleSelect(rule.id)}
                          className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                          aria-label={`Select rule ${rule.wazuh_rule_id ?? rule.id}`}
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 font-mono text-xs text-foreground">
                      {rule.wazuh_rule_id ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-foreground max-w-xs truncate">
                      {rule.description || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SCOPE_CLASSES[rule.scope] ?? ''}`}>
                        {rule.scope}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[rule.status] ?? ''}`}>
                        {rule.status}
                      </span>
                    </td>
                    {isStaff && (
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {rule.org_slug || '—'}
                      </td>
                    )}
                    <td className="px-4 py-3 text-xs">
                      {rule.incident_display_id
                        ? <a href={`/incidents/${rule.incident_display_id}`} className="text-primary hover:underline">{rule.incident_display_id}</a>
                        : <span className="text-muted-foreground">—</span>
                      }
                    </td>
                    {isStaff && (
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          {rule.status === 'pending' && (
                            <button
                              onClick={() => handleApprove(rule)}
                              className="rounded px-2 py-1 text-xs font-medium bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400"
                            >
                              Approve
                            </button>
                          )}
                          <button
                            onClick={() => setEditRule(rule)}
                            className="rounded px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400"
                          >
                            Edit
                          </button>
                          {rule.status === 'applied' && (
                            <button
                              onClick={() => handleDisable(rule)}
                              className="rounded px-2 py-1 text-xs font-medium bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400"
                            >
                              Disable
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                  {actionErrors[rule.id] && (
                    <tr className="border-b border-border last:border-0">
                      <td colSpan={colCount} className="px-4 py-1 text-xs text-red-600">
                        {actionErrors[rule.id]}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bulk action toolbar (staff only) */}
      {isStaff && selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-4 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={handleBulkApprove}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 transition-colors"
          >
            Approve selected
          </button>
          <button
            onClick={handleBulkDisable}
            className="rounded-lg px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            Disable selected
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      )}

      <EditExceptionModal
        rule={editRule}
        onClose={() => setEditRule(null)}
        onSaved={updated => { updateRule(updated); setEditRule(null); }}
      />
    </div>
  );
}
