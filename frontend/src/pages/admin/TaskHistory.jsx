import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Clock, X } from 'lucide-react';
import api from '@/lib/axios';

const POLL_MS = 30_000;

const STATUS_CLASSES = {
  SUCCESS: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  FAILURE: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  STARTED: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  PENDING: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  RETRY:   'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  REVOKED: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  );
}

function shortName(taskName) {
  if (!taskName) return '—';
  const parts = taskName.split('.');
  return parts.length > 2 ? `…${parts.slice(-2).join('.')}` : taskName;
}

function formatDuration(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatTs(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function TracebackModal({ task, onClose }) {
  if (!task) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12" onClick={onClose}>
      <div
        className="w-full max-w-3xl rounded-lg border border-border bg-card p-6 shadow-lg space-y-4 mx-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-foreground font-mono">{task.task_name}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{task.task_id}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <StatusBadge status={task.status} />
          <span>Started: {formatTs(task.date_created)}</span>
          <span>Finished: {formatTs(task.date_done)}</span>
          {task.worker && <span>Worker: {task.worker}</span>}
        </div>

        {task.traceback && (
          <div>
            <p className="text-xs font-semibold text-foreground mb-1">Traceback</p>
            <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto whitespace-pre-wrap break-all text-destructive max-h-72 overflow-y-auto">
              {task.traceback}
            </pre>
          </div>
        )}

        {task.result && (
          <div>
            <p className="text-xs font-semibold text-foreground mb-1">Result</p>
            <pre className="text-xs bg-muted rounded-md p-3 overflow-x-auto whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
              {task.result}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default function TaskHistory() {
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedTask, setSelectedTask] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const intervalRef = useRef(null);

  const fetchResults = useCallback(() => {
    const params = {};
    if (statusFilter !== 'all') params.status = statusFilter;
    if (search) params.search = search;
    api.get('/api/admin/celery/history/', { params })
      .then(res => {
        setResults(res.data.results);
        setCount(res.data.count);
        setLastUpdated(new Date());
        setError(null);
      })
      .catch(() => setError('Failed to load task history.'))
      .finally(() => setLoading(false));
  }, [statusFilter, search]);

  useEffect(() => {
    setLoading(true);
    fetchResults();
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(fetchResults, POLL_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchResults]);

  function openDetail(task) {
    if (task.status !== 'FAILURE' && task.status !== 'SUCCESS') {
      setSelectedTask(task);
      return;
    }
    setModalLoading(true);
    api.get(`/api/admin/celery/history/${task.task_id}/`)
      .then(res => setSelectedTask(res.data))
      .catch(() => setSelectedTask(task))
      .finally(() => setModalLoading(false));
  }

  const statusButtonClass = (s) => {
    const active = statusFilter === s;
    if (!active) return 'bg-muted text-muted-foreground hover:text-foreground';
    if (s === 'SUCCESS') return 'bg-green-600 text-white';
    if (s === 'FAILURE') return 'bg-red-600 text-white';
    return 'bg-primary text-primary-foreground';
  };

  const secondsAgo = lastUpdated ? Math.round((Date.now() - lastUpdated) / 1000) : null;

  return (
    <>
      {selectedTask && <TracebackModal task={selectedTask} onClose={() => setSelectedTask(null)} />}

      <div className="space-y-5 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Task History</h1>
            <p className="text-sm text-muted-foreground mt-0.5">{count} result{count !== 1 ? 's' : ''}</p>
          </div>
          {lastUpdated && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>Updated {secondsAgo}s ago</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="search"
              placeholder="Search task name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="rounded-md border border-border bg-background pl-8 pr-3 py-2 text-sm w-64 focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="flex items-center gap-1">
            {['all', 'SUCCESS', 'FAILURE', 'PENDING'].map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors ${statusButtonClass(s)}`}
              >
                {s === 'all' ? 'All' : s}
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {!loading && !error && results.length === 0 && (
          <div className="py-20 text-center rounded-xl border border-dashed border-border">
            <p className="text-sm text-muted-foreground">No task results found.</p>
          </div>
        )}

        {results.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Task</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Started</th>
                  <th className="px-4 py-3 text-left">Finished</th>
                  <th className="px-4 py-3 text-left">Duration</th>
                  <th className="px-4 py-3 text-left">Worker</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {results.map(task => (
                  <tr
                    key={task.task_id}
                    onClick={() => openDetail(task)}
                    className="hover:bg-muted/30 cursor-pointer transition-colors"
                    title={task.task_name}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-foreground max-w-xs truncate">
                      {shortName(task.task_name)}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={task.status} /></td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatTs(task.date_created)}</td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatTs(task.date_done)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDuration(task.duration)}</td>
                    <td className="px-4 py-3 text-muted-foreground font-mono text-xs truncate max-w-xs">
                      {task.worker ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {modalLoading && (
          <p className="text-xs text-muted-foreground text-center">Loading detail…</p>
        )}
      </div>
    </>
  );
}
