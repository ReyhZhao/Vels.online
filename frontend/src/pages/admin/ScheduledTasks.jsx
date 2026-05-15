import { useCallback, useEffect, useRef, useState } from 'react';
import { Clock, Play } from 'lucide-react';
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

export default function ScheduledTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toggling, setToggling] = useState({});
  const [running, setRunning] = useState({});
  const [runFeedback, setRunFeedback] = useState({});
  const [lastUpdated, setLastUpdated] = useState(null);
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

  const secondsAgo = lastUpdated ? Math.round((Date.now() - lastUpdated) / 1000) : null;

  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Scheduled Tasks</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{tasks.length} task{tasks.length !== 1 ? 's' : ''}</p>
        </div>
        {lastUpdated && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>Updated {secondsAgo}s ago</span>
          </div>
        )}
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && tasks.length === 0 && (
        <div className="py-20 text-center rounded-xl border border-dashed border-border">
          <p className="text-sm text-muted-foreground">No scheduled tasks found.</p>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Task</th>
                <th className="px-4 py-3 text-left">Schedule</th>
                <th className="px-4 py-3 text-left">Last run</th>
                <th className="px-4 py-3 text-left">Next run</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {tasks.map(task => (
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
