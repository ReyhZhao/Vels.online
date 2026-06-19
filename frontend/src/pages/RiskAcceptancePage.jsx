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

  const fetchAcceptances = useCallback(async (slug) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/security/risk-acceptances/?org=${slug}`);
      setAcceptances(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load risk acceptances.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrg) fetchAcceptances(selectedOrg.slug);
  }, [selectedOrg, fetchAcceptances]);

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

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">CVE ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">CVSS</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Accepted By</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Accepted At</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Note</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                  No accepted vulnerabilities.
                </td>
              </tr>
            ) : (
              filtered.map(a => (
                <tr key={a.id} className="border-b border-border last:border-0">
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
    </div>
  );
}
