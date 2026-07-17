import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/axios';

function formatTs(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

const SORT_COLUMNS = { sender: 'Sender', drop_reason: 'Reason', received_at: 'Received' };

export default function IntakeInbox() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [reasonFilter, setReasonFilter] = useState('all');
  const [sortKey, setSortKey] = useState('received_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [replayingId, setReplayingId] = useState(null);

  function load() {
    return api.get('/api/partners/intake-inbox/')
      .then(res => setRows(res.data))
      .catch(() => setError('Failed to load the Intake Inbox.'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function dismiss(row) {
    try {
      await api.delete(`/api/partners/intake-inbox/${row.id}/`);
      setRows(prev => prev.filter(r => r.id !== row.id));
    } catch {
      setError('Failed to dismiss the row.');
    }
  }

  // Replay the whole covered backlog for this row's Connection, then refresh so newly
  // created "Replayed → INC-…" links appear (ADR-0035).
  async function replay(row) {
    setError(null);
    setReplayingId(row.id);
    try {
      await api.post(`/api/partners/connections/${row.covering_connection.id}/replay-intake/`);
      await load();
    } catch {
      setError('Failed to replay held messages.');
    } finally {
      setReplayingId(null);
    }
  }

  function RowActions({ row }) {
    if (row.replayed_incident) {
      return (
        <Link to={`/incidents/${row.replayed_incident.id}`} className="text-xs text-primary hover:underline">
          Replayed → {row.replayed_incident.display_id}
        </Link>
      );
    }
    if (row.covering_connection && row.has_raw) {
      return (
        <button onClick={() => replay(row)} disabled={replayingId === row.id}
          className="text-xs text-primary hover:underline disabled:opacity-50">
          {replayingId === row.id ? 'Replaying…' : `Replay → ${row.covering_connection.name}`}
        </button>
      );
    }
    return (
      <Link to={`/admin/partners/connections?sender=${encodeURIComponent(row.sender)}`} className="text-xs text-primary hover:underline">
        Create Connection
      </Link>
    );
  }

  function setSort(key) {
    if (sortKey === key) setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortOrder(key === 'received_at' ? 'desc' : 'asc'); }
  }

  const reasons = useMemo(() => [...new Set(rows.map(r => r.drop_reason).filter(Boolean))].sort(), [rows]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = rows.filter(r => {
      if (reasonFilter !== 'all' && r.drop_reason !== reasonFilter) return false;
      if (!q) return true;
      return (
        (r.sender || '').toLowerCase().includes(q) ||
        (r.subject || '').toLowerCase().includes(q) ||
        (r.drop_reason || '').toLowerCase().includes(q)
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    out = [...out].sort((a, b) =>
      (a[sortKey] || '').toString().toLowerCase().localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir,
    );
    return out;
  }, [rows, search, reasonFilter, sortKey, sortOrder]);

  function SortHeader({ field }) {
    return (
      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <button onClick={() => setSort(field)} aria-label={`Sort by ${SORT_COLUMNS[field]}`}
          className="flex items-center gap-1 uppercase hover:text-foreground transition-colors">
          {SORT_COLUMNS[field]}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Intake Inbox</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Inbound email that reached the SOC mailbox but no handler accepted — unknown senders,
          failed verification, or un-routable mail. Onboard a partner with "Create Connection".
        </p>
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input type="search" placeholder="Search inbox…" value={search} onChange={e => setSearch(e.target.value)}
          aria-label="Search intake inbox"
          className="w-52 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring" />
        <select value={reasonFilter} onChange={e => setReasonFilter(e.target.value)} aria-label="Reason filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground">
          <option value="all">All reasons</option>
          {reasons.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>

      {/* Mobile cards */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Intake Inbox is empty.</p>
        ) : visible.map(r => (
          <div key={r.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-1">
            <p className="font-mono text-sm text-foreground">{r.sender || '(no sender)'}</p>
            <p className="text-xs text-muted-foreground">{r.subject}</p>
            <p className="text-xs"><span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">{r.drop_reason}</span></p>
            <p className="text-xs text-muted-foreground">{formatTs(r.received_at)}</p>
            <div className="flex gap-2 pt-1">
              <RowActions row={r} />
              <button onClick={() => dismiss(r)} className="text-xs text-muted-foreground hover:underline">Dismiss</button>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block rounded-lg border border-border bg-card">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border">
              <SortHeader field="sender" />
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Subject</th>
              <SortHeader field="drop_reason" />
              <SortHeader field="received_at" />
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">Intake Inbox is empty.</td></tr>
            ) : visible.map(r => (
              <tr key={r.id} className="border-b border-border last:border-0 hover:bg-accent/20">
                <td className="px-4 py-3 font-mono text-sm text-foreground">{r.sender || '(no sender)'}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate" title={r.subject}>{r.subject}</td>
                <td className="px-4 py-3 text-xs"><span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">{r.drop_reason}</span></td>
                <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">{formatTs(r.received_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-3">
                    <RowActions row={r} />
                    <button onClick={() => dismiss(r)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Dismiss</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
