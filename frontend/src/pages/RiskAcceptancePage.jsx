import { useState, useEffect, useCallback } from 'react';
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
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low}`}>
      {severity}
    </span>
  );
}

function RemoveConfirmDialog({ cveId, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-foreground">Remove risk acceptance?</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This will remove the acceptance for{' '}
          <span className="font-mono font-medium text-foreground">{cveId}</span> and revert all
          related work package items back to open.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            aria-label="Confirm remove"
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low'];

export default function RiskAcceptancePage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [acceptances, setAcceptances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [confirmId, setConfirmId] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkConfirm, setBulkConfirm] = useState(false);
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

  const fetchAcceptances = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/security/risk-acceptances/?org=${slug}`);
      setAcceptances(res.data);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load risk acceptances.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrg) fetchAcceptances(selectedOrg.slug);
  }, [selectedOrg, fetchAcceptances]);

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleBulkRemove() {
    const ids = [...selectedIds];
    for (const id of ids) {
      try {
        await api.delete(`/api/security/risk-acceptances/${id}/`);
        setAcceptances(prev => prev.filter(a => a.id !== id));
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to remove one or more risk acceptances.');
      }
    }
    setSelectedIds(new Set());
    setBulkConfirm(false);
  }

  async function handleRemove() {
    if (!confirmId || removing) return;
    setRemoving(true);
    try {
      await api.delete(`/api/security/risk-acceptances/${confirmId}/`);
      setAcceptances(prev => prev.filter(a => a.id !== confirmId));
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to remove risk acceptance.');
    } finally {
      setRemoving(false);
      setConfirmId(null);
    }
  }

  const confirmItem = acceptances.find(a => a.id === confirmId);

  const filtered = acceptances.filter(a => {
    const matchSev = !severityFilter || a.severity === severityFilter;
    const q = search.toLowerCase();
    const matchSearch = !q ||
      (a.cve_id || '').toLowerCase().includes(q) ||
      (a.accepted_by || '').toLowerCase().includes(q) ||
      (a.note || '').toLowerCase().includes(q);
    return matchSev && matchSearch;
  });

  const sorted = sortKey
    ? [...filtered].sort((a, b) => {
        const dir = sortOrder === 'asc' ? 1 : -1;
        if (sortKey === 'cvss') {
          const av = a.cvss_score ?? -1, bv = b.cvss_score ?? -1;
          return (av - bv) * dir;
        }
        if (sortKey === 'accepted_at') {
          const av = a.accepted_at ? new Date(a.accepted_at).getTime() : 0;
          const bv = b.accepted_at ? new Date(b.accepted_at).getTime() : 0;
          return (av - bv) * dir;
        }
        return (a.cve_id || '').localeCompare(b.cve_id || '') * dir;
      })
    : filtered;

  const allSelected = sorted.length > 0 && sorted.every(a => selectedIds.has(a.id));

  function toggleSelectAll() {
    setSelectedIds(allSelected ? new Set() : new Set(sorted.map(a => a.id)));
  }

  if (orgLoading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;
  if (!selectedOrg) return <p className="text-sm text-muted-foreground p-6">No organisation assigned.</p>;

  return (
    <div className="space-y-6 p-6">
      {confirmItem && (
        <RemoveConfirmDialog
          cveId={confirmItem.cve_id}
          onConfirm={handleRemove}
          onCancel={() => setConfirmId(null)}
        />
      )}

      {bulkConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-foreground">Remove {selectedIds.size} risk acceptances?</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This will remove the selected acceptances and revert their related work package items back to open.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setBulkConfirm(false)} className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent">Cancel</button>
              <button onClick={handleBulkRemove} aria-label="Confirm bulk remove" className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700">Remove selected</button>
            </div>
          </div>
        </div>
      )}

      <h1 className="text-2xl font-semibold text-foreground">
        Accepted Vulnerabilities — {selectedOrg.name}
      </h1>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search CVE, accepted by…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search risk acceptances"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={severityFilter}
          onChange={e => setSeverityFilter(e.target.value)}
          aria-label="Severity filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All severities</option>
          {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : sorted.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No accepted vulnerabilities.</p>
        ) : sorted.map(a => (
          <div key={a.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedIds.has(a.id)}
                onChange={() => toggleSelect(a.id)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                aria-label={`Select ${a.cve_id}`}
              />
              <span className="font-mono text-xs font-medium text-foreground">{a.cve_id}</span>
              <span className="ml-auto"><SeverityBadge severity={a.severity} /></span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>CVSS {a.cvss_score != null ? a.cvss_score.toFixed(1) : '—'}</span>
              <span>{a.accepted_by || '—'}</span>
              <span className="ml-auto">{a.accepted_at ? new Date(a.accepted_at).toLocaleDateString() : '—'}</span>
            </div>
            {a.note && <p className="text-xs text-muted-foreground">{a.note}</p>}
            <div className="pt-1">
              <button
                onClick={() => setConfirmId(a.id)}
                disabled={removing}
                className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
              >
                Remove
              </button>
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
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('cve_id')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by CVE ID">
                  CVE ID
                  {sortKey === 'cve_id' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('cvss')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Severity">
                  Severity
                  {sortKey === 'cvss' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">CVSS</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Accepted By</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('accepted_at')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Accepted At">
                  Accepted At
                  {sortKey === 'accepted_at' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Note</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                  No accepted vulnerabilities.
                </td>
              </tr>
            ) : (
              sorted.map(a => (
                <tr key={a.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(a.id)}
                      onChange={() => toggleSelect(a.id)}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                      aria-label={`Select ${a.cve_id}`}
                    />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">{a.cve_id}</td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={a.severity} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {a.cvss_score != null ? a.cvss_score.toFixed(1) : '—'}
                  </td>
                  <td className="px-4 py-3 text-foreground">{a.accepted_by || '—'}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {a.accepted_at ? new Date(a.accepted_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground max-w-xs truncate">
                    {a.note || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setConfirmId(a.id)}
                      disabled={removing}
                      className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bulk remove toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-4 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={() => setBulkConfirm(true)}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
          >
            Remove selected
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
