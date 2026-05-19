import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';

const LOG_TYPES = [
  { key: 'accesslog',   label: 'Access Logs' },
  { key: 'modsecurity', label: 'WAF Blocks' },
];

function formatTimestamp(ts) {
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

export default function RouteReports({ fqdn }) {
  const [logType, setLogType]       = useState('accesslog');
  const [srcipInput, setSrcipInput] = useState('');
  const [activeSrcip, setActiveSrcip] = useState(null);
  const [logs, setLogs]             = useState([]);
  const [summary, setSummary]       = useState({ total: 0, blocked: 0 });
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const fetchLogs = useCallback((type, srcip) => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ type });
    if (srcip) params.set('srcip', srcip);
    api.get(`/api/ingress/routes/${fqdn}/logs/?${params}`)
      .then(res => {
        setLogs(res.data.logs ?? []);
        setSummary(res.data.summary ?? { total: 0, blocked: 0 });
      })
      .catch(() => setError('Failed to load logs.'))
      .finally(() => setLoading(false));
  }, [fqdn]);

  useEffect(() => {
    fetchLogs(logType, activeSrcip);
  }, [fetchLogs, logType, activeSrcip]);

  function handleTabSwitch(key) {
    setLogType(key);
  }

  function handleFilterSubmit(e) {
    e.preventDefault();
    setActiveSrcip(srcipInput.trim() || null);
  }

  function handleFilterClear() {
    setSrcipInput('');
    setActiveSrcip(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex gap-1 border border-border rounded-md p-1">
          {LOG_TYPES.map(t => (
            <button
              key={t.key}
              onClick={() => handleTabSwitch(t.key)}
              className={`px-3 py-1 text-sm rounded font-medium transition-colors ${
                logType === t.key
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleFilterSubmit} className="flex items-center gap-2">
          <input
            type="text"
            value={srcipInput}
            onChange={e => setSrcipInput(e.target.value)}
            placeholder="Filter by IP…"
            aria-label="Filter by source IP"
            className="h-8 rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="submit"
            className="h-8 rounded-md border border-border px-3 text-sm hover:bg-accent transition-colors"
          >
            Filter
          </button>
          {activeSrcip && (
            <button
              type="button"
              onClick={handleFilterClear}
              className="h-8 rounded-md border border-border px-3 text-sm hover:bg-accent transition-colors"
            >
              Clear
            </button>
          )}
        </form>
      </div>

      <div className="flex items-center gap-4 text-sm">
        <span className="text-muted-foreground">
          Total: <span className="font-medium text-foreground">{summary.total.toLocaleString()}</span>
        </span>
        <span className="text-muted-foreground">
          Blocked: <span className="font-medium text-destructive">{summary.blocked.toLocaleString()}</span>
        </span>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground" data-testid="logs-loading">Loading logs…</p>
      ) : error ? (
        <div className="space-y-2">
          <p className="text-sm text-destructive">{error}</p>
          <button
            onClick={() => fetchLogs(logType, activeSrcip)}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent transition-colors"
          >
            Retry
          </button>
        </div>
      ) : logs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No log entries found for this route.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Timestamp</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Source IP</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Request</th>
                {logType === 'accesslog' ? (
                  <>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Size</th>
                  </>
                ) : (
                  <>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule ID</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">Country</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.map((log, i) => {
                const d   = log.data ?? {};
                const geo = log.GeoLocation ?? {};
                return (
                  <tr key={log._id || i} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{d.srcip ?? '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      <span className="font-medium">{d.http_method}</span>{' '}
                      <span className="text-muted-foreground">{d.http_path}</span>
                    </td>
                    {logType === 'accesslog' ? (
                      <>
                        <td className="px-4 py-3 font-mono text-xs">{d.status_code ?? '—'}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {d.body_bytes_sent != null ? `${d.body_bytes_sent}B` : '—'}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-3 font-mono text-xs">{d.ruleid ?? '—'}</td>
                        <td className="px-4 py-3 text-xs">{geo.country_name ?? '—'}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
