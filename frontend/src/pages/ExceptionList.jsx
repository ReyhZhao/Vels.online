import { useState, useEffect } from 'react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';

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

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Exception Rules</h1>
        {!loading && <span className="text-sm text-muted-foreground">{rules.length} total</span>}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
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

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Scope</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              {isStaff && <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organisation</th>}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Incident</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={isStaff ? 6 : 5} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : rules.length === 0 ? (
              <tr>
                <td colSpan={isStaff ? 6 : 5} className="px-4 py-8 text-center text-muted-foreground">
                  No exception rules.
                </td>
              </tr>
            ) : (
              rules.map(rule => (
                <tr key={rule.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
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
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
