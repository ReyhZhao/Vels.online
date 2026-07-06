import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Clock, Play, ArrowUp, ArrowDown, ChevronsUpDown, Search } from 'lucide-react';
import api from '@/lib/axios';

const POLL_MS = 30_000;

function formatTs(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function humanSchedule(display) {
  if (!display || display === 'unknown') return '—';
  // IntervalSchedule already returns e.g. "every 24 hours"
  // CrontabSchedule we stored as "min hour dom month dow"
  const parts = display.split(' ');
  if (parts.length === 5) {
    return `cron: ${display}`;
  }
  return display;
}

// Columns that can be sorted. `get` returns a comparable value; nulls sort last.
const COLUMNS = [
  { key: 'name', label: 'Name', get: t => (t.name || '').toLowerCase() },
  { key: 'task', label: 'Task', get: t => (t.task || '').toLowerCase() },
  { key: 'schedule', label: 'Schedule', get: t => (t.schedule_display || '').toLowerCase() },
  { key: 'last_run_at', label: 'Last run', get: t => (t.last_run_at ? new Date(t.last_run_at).getTime() : null) },
  { key: 'next_run', label: 'Next run', get: t => (t.next_run ? new Date(t.next_run).getTime() : null) },
  { key: 'enabled', label: 'Status', get: t => (t.enabled ? 1 : 0) },
];

export default function ScheduledTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toggling, setToggling] = useState({});
  const [running, setRunning] = useState({});
  const [runFeedback, setRunFeedback] = useState({});
  const [lastUpdated, setLastUpdated] = useState(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all'); // all | enabled | disabled
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
  const intervalRef = useRef(null);

  const fetchTasks = useCallback(() => {
    api.get('/api/admin/celery/scheduled/')
      .then(res => {
        setTasks(res.data);
        setLastUpdated(new Date());
        setError(null);
      })
      .catch(() => setError('Failed to load scheduled tasks.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchTasks();
    intervalRef.current = setInterval(fetchTasks, POLL_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchTasks]);

  async function toggleEnabled(task) {
    setToggling(prev => ({ ...prev, [task.id]: true }));
    try {
      const res = await api.patch(`/api/admin/celery/scheduled/${task.id}/`, {
        enabled: !task.enabled,
      });
      setTasks(prev => prev.map(t => (t.id === task.id ? res.data : t)));
    } catch {
      // silently leave state unchanged; user will see it revert
    } finally {
      setToggling(prev => ({ ...prev, [task.id]: false }));
    }
  }

  async function runNow(task) {
    setRunning(prev => ({ ...prev, [task.id]: true }));
    setRunFeedback(prev => ({ ...prev, [task.id]: null }));
    try {
      const res = await api.post(`/api/admin/celery/scheduled/${task.id}/run/`);
      setRunFeedback(prev => ({ ...prev, [task.id]: `Queued: ${res.data.task_id.slice(0, 8)}…` }));
    } catch {
      setRunFeedback(prev => ({ ...prev, [task.id]: 'Failed to queue.' }));
    } finally {
      setRunning(prev => ({ ...prev, [task.id]: false }));
    }
  }

  function toggleSort(key) {
    setSort(prev => (prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  }

  const visibleTasks = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = tasks.filter(t => {
      if (status === 'enabled' && !t.enabled) return false;
      if (status === 'disabled' && t.enabled) return false;
      if (q) {
        const hay = `${t.name || ''} ${t.task || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    const col = COLUMNS.find(c => c.key === sort.key) ?? COLUMNS[0];
    const factor = sort.dir === 'asc' ? 1 : -1;
    rows = [...rows].sort((ra, rb) => {
      const a = col.get(ra);
      const b = col.get(rb);
      if (a === null && b === null) return 0;
      if (a === null) return 1; // nulls last
      if (b === null) return -1;
      if (a < b) return -1 * factor;
      if (a > b) return 1 * factor;
      return 0;
    });
    return rows;
  }, [tasks, query, status, sort]);

  const secondsAgo = lastUpdated ? Math.round((Date.now() - lastUpdated) / 1000) : null;

  function SortIcon({ colKey }) {
    if (sort.key !== colKey) return <ChevronsUpDown className="h-3 w-3 opacity-40" />;
    return sort.dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
  }

  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Scheduled Tasks</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {visibleTasks.length === tasks.length
              ? `${tasks.length} task${tasks.length !== 1 ? 's' : ''}`
              : `${visibleTasks.length} of ${tasks.length} task${tasks.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        {lastUpdated && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>Updated {secondsAgo}s ago</span>
          </div>
        )}
      </div>

      {!loading && !error && tasks.length > 0 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by name or task…"
              aria-label="Search tasks"
              className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            aria-label="Status filter"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="all">All statuses</option>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </select>
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && tasks.length === 0 && (
        <div className="py-20 text-center rounded-xl border border-dashed border-border">
          <p className="text-sm text-muted-foreground">No scheduled tasks found.</p>
        </div>
      )}

      {!loading && !error && tasks.length > 0 && visibleTasks.length === 0 && (
        <div className="py-20 text-center rounded-xl border border-dashed border-border">
          <p className="text-sm text-muted-foreground">No tasks match your search.</p>
        </div>
      )}

      {visibleTasks.length > 0 && (
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground uppercase tracking-wider">
              <tr>
                {COLUMNS.map(col => (
                  <th key={col.key} className="px-4 py-3 text-left">
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      aria-label={`Sort by ${col.label}`}
                      className="inline-flex items-center gap-1 uppercase tracking-wider hover:text-foreground transition-colors"
                    >
                      {col.label}
                      <SortIcon colKey={col.key} />
                    </button>
                  </th>
                ))}
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visibleTasks.map(task => (
                <tr key={task.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{task.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-xs" title={task.task}>
                    {task.task}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{humanSchedule(task.schedule_display)}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">{formatTs(task.last_run_at)}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">{formatTs(task.next_run)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${task.enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
                      {task.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleEnabled(task)}
                        disabled={toggling[task.id]}
                        className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
                      >
                        {toggling[task.id] ? '…' : task.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={() => runNow(task)}
                        disabled={running[task.id]}
                        className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                      >
                        <Play className="h-3 w-3" />
                        {running[task.id] ? 'Queuing…' : 'Run now'}
                      </button>
                      {runFeedback[task.id] && (
                        <span className={`text-xs ${runFeedback[task.id].startsWith('Queued') ? 'text-green-600' : 'text-destructive'}`}>
                          {runFeedback[task.id]}
                        </span>
                      )}
                    </div>
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
