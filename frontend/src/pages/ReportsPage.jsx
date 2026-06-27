import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';

const AUDIENCE_BADGE = {
  customer: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  internal: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

function formatWhen(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ReportsPage() {
  const { user } = useAuth();
  const isStaff = user?.is_staff ?? false;

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get('/api/incidents/reports/');
        if (active) setReports(res.data);
      } catch {
        if (active) setError('Failed to load reports.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function handleDownload(report) {
    try {
      const res = await api.get(
        `/api/incidents/${report.incident_display_id}/reports/${report.id}/download/`
      );
      window.open(res.data.url, '_blank', 'noopener,noreferrer');
    } catch {
      setError('Failed to open report.');
    }
  }

  const filtered = reports.filter((r) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      r.reference_id?.toLowerCase().includes(q) ||
      r.template_name?.toLowerCase().includes(q) ||
      r.organization_name?.toLowerCase().includes(q) ||
      r.incident_display_id?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Reports</h1>
        <p className="text-sm text-muted-foreground">
          {isStaff
            ? 'All generated incident reports across customers.'
            : 'Reports shared with your organisation.'}
        </p>
      </div>

      {reports.length > 0 && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by reference, template, customer or incident…"
          className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
          aria-label="Search reports"
        />
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading reports…</p>
      ) : error ? (
        <p className="text-sm italic text-muted-foreground">{error}</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No reports found.</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2">Template</th>
                {isStaff && <th className="px-3 py-2">Audience</th>}
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Incident</th>
                <th className="px-3 py-2">Generated</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((r) => (
                <tr key={r.id} className="hover:bg-muted/20">
                  <td className="px-3 py-2 font-mono">{r.reference_id}</td>
                  <td className="px-3 py-2">{r.template_name}</td>
                  {isStaff && (
                    <td className="px-3 py-2">
                      <span className={`rounded px-1 text-xs ${AUDIENCE_BADGE[r.audience] || ''}`}>
                        {r.audience}
                      </span>
                    </td>
                  )}
                  <td className="px-3 py-2">{r.organization_name || '—'}</td>
                  <td className="px-3 py-2">
                    <Link to={`/incidents/${r.incident_display_id}`} className="text-primary hover:underline">
                      {r.incident_display_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{formatWhen(r.generated_at)}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => handleDownload(r)} className="text-primary hover:underline">
                      Download
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
