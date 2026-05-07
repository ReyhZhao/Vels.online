import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

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

function Badge({ value, classes }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes[value] ?? classes.info ?? ''}`}>
      {value}
    </span>
  );
}

export default function IncidentList() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/api/incidents/');
      setIncidents(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load incidents.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  if (orgLoading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Incidents</h1>

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
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organisation</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : incidents.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No incidents.</td>
              </tr>
            ) : (
              incidents.map(inc => (
                <tr key={inc.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">
                    <Link to={`/incidents/${inc.id}`} className="hover:underline">{inc.display_id}</Link>
                  </td>
                  <td className="px-4 py-3 text-foreground max-w-xs truncate">
                    <Link to={`/incidents/${inc.id}`} className="hover:underline">{inc.title}</Link>
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={inc.severity} classes={SEVERITY_CLASSES} />
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={`TLP:${inc.tlp.toUpperCase()}`} classes={{ [`TLP:${inc.tlp.toUpperCase()}`]: TLP_CLASSES[inc.tlp] }} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground capitalize">{inc.state}</td>
                  <td className="px-4 py-3 text-muted-foreground">{inc.org_slug}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {inc.created_at ? new Date(inc.created_at).toLocaleDateString() : '—'}
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
