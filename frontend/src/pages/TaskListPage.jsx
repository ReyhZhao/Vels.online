import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../lib/axios';

const TASK_STATE_LABELS = {
  new:         'New',
  in_progress: 'In Progress',
  done:        'Done',
  cancelled:   'Cancelled',
};

const TASK_STATE_CLASSES = {
  new:         'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  done:        'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled:   'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const STATE_OPTIONS = ['new', 'in_progress', 'done', 'cancelled'];

const SORT_COLUMNS = {
  title:      { label: 'Title',    defaultOrder: 'asc'  },
  state:      { label: 'State',    defaultOrder: 'asc'  },
  assignee:   { label: 'Assignee', defaultOrder: 'asc'  },
  incident:   { label: 'Incident', defaultOrder: 'asc'  },
  created_at: { label: 'Created',  defaultOrder: 'desc' },
};

const EMPTY_DATA = { count: 0, page: 1, per_page: 25, total_pages: 1, results: [] };

export default function TaskListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const [data, setData]     = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [staffUsers, setStaffUsers] = useState([]);
  const [reassignTarget, setReassignTarget] = useState('');
  const [reassigning, setReassigning] = useState(false);

  const fetchTasks = useCallback(async (params) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/api/tasks/', { params });
      setData(res.data);
      setSelectedIds(new Set());
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load tasks.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.get('/api/incidents/staff-users/')
      .then(res => setStaffUsers(res.data || []))
      .catch(() => {});
  }, []);

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll(rows) {
    const ids = rows.map(t => t.id);
    const allSelected = ids.length > 0 && ids.every(id => selectedIds.has(id));
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) ids.forEach(id => next.delete(id));
      else ids.forEach(id => next.add(id));
      return next;
    });
  }

  async function handleBulkReassign() {
    if (reassignTarget === '') return;
    const assignee = reassignTarget === 'unassign' ? null : Number(reassignTarget);
    const ids = [...selectedIds];
    setReassigning(true);
    try {
      for (const id of ids) {
        try {
          await api.patch(`/api/tasks/${id}/`, { assignee });
        } catch {
          setError('Failed to reassign one or more tasks.');
        }
      }
      setReassignTarget('');
      fetchTasks(Object.fromEntries(searchParams.entries()));
    } finally {
      setReassigning(false);
    }
  }

  useEffect(() => {
    if (!searchParams.has('assignee')) {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        next.set('assignee', 'me');
        return next;
      }, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchTasks(Object.fromEntries(searchParams.entries()));
  }, [searchParams, fetchTasks]);

  function setParam(key, value) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('page');
      return next;
    });
  }

  function setPage(p) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('page', p);
      return next;
    });
  }

  const sortKey = searchParams.get('sort') || '';
  const sortOrder = searchParams.get('order') || 'asc';

  function setSort(field) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (sortKey === field) {
        next.set('order', sortOrder === 'asc' ? 'desc' : 'asc');
      } else {
        next.set('sort', field);
        next.set('order', SORT_COLUMNS[field]?.defaultOrder ?? 'asc');
      }
      next.delete('page');
      return next;
    });
  }

  const { results, count, page, total_pages } = data;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Tasks</h1>
        {!loading && <span className="text-sm text-muted-foreground">{count} total</span>}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search by title…"
          value={searchParams.get('q') || ''}
          onChange={e => setParam('q', e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
          aria-label="Search tasks"
        />
        <select
          value={searchParams.get('state') || ''}
          onChange={e => setParam('state', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="State filter"
        >
          <option value="">All states</option>
          {STATE_OPTIONS.map(s => (
            <option key={s} value={s}>{TASK_STATE_LABELS[s]}</option>
          ))}
        </select>
        <select
          value={searchParams.get('assignee') || 'me'}
          onChange={e => setParam('assignee', e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Assignee filter"
        >
          <option value="me">My tasks</option>
          <option value="">All assignees</option>
          <option value="unassigned">Unassigned</option>
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : results.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No tasks found.</p>
        ) : results.map(task => (
          <div key={task.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedIds.has(task.id)}
                onChange={() => toggleSelect(task.id)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                aria-label={`Select ${task.title}`}
              />
              <span className="text-sm font-medium text-foreground leading-snug flex-1">{task.title}</span>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TASK_STATE_CLASSES[task.state] ?? ''}`}>
                {TASK_STATE_LABELS[task.state] ?? task.state}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>{task.assignee_username ?? 'Unassigned'}</span>
              {task.incident_display_id && (
                <Link to={`/incidents/${task.incident_display_id}`} className="font-mono text-primary hover:underline">
                  {task.incident_display_id}
                </Link>
              )}
              <span className="ml-auto">{task.created_at ? new Date(task.created_at).toLocaleDateString() : '—'}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  checked={results.length > 0 && results.every(t => selectedIds.has(t.id))}
                  onChange={() => toggleSelectAll(results)}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </th>
              {['title', 'state', 'assignee', 'incident', 'created_at'].map(field => (
                <th key={field} className="px-4 py-3 text-left font-medium text-muted-foreground">
                  <button
                    onClick={() => setSort(field)}
                    className="flex items-center gap-1 hover:text-foreground transition-colors"
                    aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
                  >
                    {SORT_COLUMNS[field].label}
                    {sortKey === field && (
                      <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No tasks found.</td>
              </tr>
            ) : (
              results.map(task => (
                <tr key={task.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(task.id)}
                      onChange={() => toggleSelect(task.id)}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                      aria-label={`Select ${task.title}`}
                    />
                  </td>
                  <td className="px-4 py-3 text-foreground max-w-xs truncate">{task.title}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TASK_STATE_CLASSES[task.state] ?? ''}`}>
                      {TASK_STATE_LABELS[task.state] ?? task.state}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{task.assignee_username ?? '—'}</td>
                  <td className="px-4 py-3">
                    {task.incident_display_id ? (
                      <Link
                        to={`/incidents/${task.incident_display_id}`}
                        className="text-primary hover:underline font-mono text-xs"
                        onClick={e => e.stopPropagation()}
                      >
                        {task.incident_display_id}
                        {task.incident_title && (
                          <span className="ml-1 font-sans text-muted-foreground">— {task.incident_title}</span>
                        )}
                      </Link>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                    {task.created_at ? new Date(task.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bulk reassign toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-background px-6 py-3 shadow-2xl">
          <span className="text-sm text-foreground">{selectedIds.size} selected</span>
          <select
            value={reassignTarget}
            onChange={e => setReassignTarget(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
            aria-label="Reassign to"
          >
            <option value="">Reassign to…</option>
            <option value="unassign">Unassigned</option>
            {staffUsers.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
          <button
            onClick={handleBulkReassign}
            disabled={reassignTarget === '' || reassigning}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {reassigning ? 'Reassigning…' : 'Apply'}
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      )}

      {total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page} of {total_pages} ({count} total)
          </p>
          <div className="flex gap-1">
            {Array.from({ length: total_pages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                disabled={p === page}
                className={`rounded px-3 py-1 text-sm transition-colors ${
                  p === page
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border hover:bg-accent text-foreground'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
