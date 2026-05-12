import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';

function formatTimestamp(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export default function RouteReports({ fqdn }) {
  const [entries, setEntries] = useState([]);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchReports = useCallback(() => {
    setLoading(true);
    setError(null);
    setMessage(null);
    api.get(`/api/ingress/routes/${fqdn}/reports/`)
      .then(res => {
        setEntries(res.data.entries ?? []);
        setMessage(res.data.message ?? null);
      })
      .catch(() => setError('Failed to load reports.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  if (loading) {
    return <p className="text-sm text-muted-foreground" data-testid="reports-loading">Loading reports…</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-destructive">{error}</p>
        <button
          onClick={fetchReports}
          className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (message) {
    return <p className="text-sm text-muted-foreground">{message}</p>;
  }

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No blocked activity recorded for this route.</p>;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Timestamp</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Source IP</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {entries.map((entry, i) => (
            <tr key={i} className="hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                {formatTimestamp(entry.timestamp)}
              </td>
              <td className="px-4 py-3 font-mono text-xs">{entry.ip}</td>
              <td className="px-4 py-3">{entry.rule}</td>
              <td className="px-4 py-3 capitalize">{entry.action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
