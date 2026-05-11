import { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import IncidentComments from '../components/IncidentComments';

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

const ALL_STATES = ['new', 'in_progress', 'done', 'cancelled'];

// ── Task modal ────────────────────────────────────────────────────────────────

function TaskModal({ task, onClose, onUpdate, currentUserId, isStaff }) {
  const [currentTask, setCurrentTask] = useState(task);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  async function changeState(newState) {
    setSaving(true);
    setError(null);
    try {
      const res = await api.patch(`/api/tasks/${currentTask.id}/`, { state: newState });
      setCurrentTask(res.data);
      onUpdate(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update task.');
    } finally {
      setSaving(false);
    }
  }

  const nextStates = ALL_STATES.filter(s => s !== currentTask.state);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex w-full max-w-2xl max-h-[90vh] flex-col rounded-lg border border-border bg-card shadow-xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="flex flex-col gap-1.5 min-w-0">
            <h2 className="text-base font-semibold text-foreground">{currentTask.title}</h2>
            {currentTask.template_name && (
              <span className="inline-flex w-fit items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {currentTask.template_name}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Description */}
          {currentTask.description ? (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentTask.description}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">No description.</p>
          )}

          {/* State badge + action buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TASK_STATE_CLASSES[currentTask.state] ?? ''}`}>
              {TASK_STATE_LABELS[currentTask.state] ?? currentTask.state}
            </span>
            {nextStates.map(s => (
              <button
                key={s}
                onClick={() => changeState(s)}
                disabled={saving}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
              >
                {TASK_STATE_LABELS[s]}
              </button>
            ))}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          {/* Task-scoped comments */}
          <div className="border-t border-border pt-4">
            <IncidentComments
              incidentId={currentTask.incident}
              taskId={currentTask.id}
              currentUserId={currentUserId}
              isStaff={isStaff}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Task row (read-only, clickable) ───────────────────────────────────────────

function TaskRow({ task, onSelect }) {
  const isCancelled     = task.state === 'cancelled';
  const isTemplateDerived = task.template_name !== null;

  return (
    <tr
      className={`border-b border-border last:border-0 cursor-pointer transition-colors ${
        isCancelled ? 'opacity-60' : 'hover:bg-accent/20'
      }`}
      onClick={() => onSelect(task)}
    >
      <td className="px-3 py-2 text-xs text-muted-foreground w-8">{task.display_order}</td>
      <td className="px-3 py-2 text-sm font-medium text-foreground">
        <div className="flex items-center gap-2">
          <span
            className={isCancelled ? 'line-through text-muted-foreground' : ''}
            title={isCancelled && isTemplateDerived ? 'Auto-cancelled when subject changed' : undefined}
          >
            {task.title}
          </span>
          {isTemplateDerived && (
            <span className="shrink-0 inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              template
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TASK_STATE_CLASSES[task.state] ?? ''}`}>
          {TASK_STATE_LABELS[task.state] ?? task.state}
        </span>
      </td>
    </tr>
  );
}

function TaskGroup({ groupName, tasks, onSelect }) {
  return (
    <div className="space-y-1">
      <p className="px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {groupName}
      </p>
      <div className="overflow-hidden rounded border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground w-8">#</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Title</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">State</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(task => (
              <TaskRow key={task.id} task={task} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Add-hoc form (unchanged) ──────────────────────────────────────────────────

function AddAdHocForm({ incidentId, onAdded }) {
  const [title, setTitle] = useState('');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const res = await api.post(`/api/incidents/${incidentId}/tasks/`, {
        title: title.trim(),
        display_order: 0,
      });
      onAdded(res.data);
      setTitle('');
    } catch (err) {
      setError(err.response?.data?.title?.[0] || 'Failed to add task.');
    } finally {
      setAdding(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-center">
      <input
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="Ad-hoc task title"
        disabled={adding}
        className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={adding || !title.trim()}
        className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        Add task
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}

// ── Template picker (unchanged) ───────────────────────────────────────────────

function TemplatePicker({ incidentId, subjectId, onApplied }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [applying, setApplying]   = useState(null);
  const [error, setError]         = useState(null);

  useEffect(() => {
    if (!subjectId) {
      setLoading(false);
      return;
    }
    api.get(`/api/task-templates/?subject=${subjectId}`)
      .then(res => setTemplates(res.data.filter(t => !t.archived)))
      .catch(() => setError('Failed to load templates.'))
      .finally(() => setLoading(false));
  }, [subjectId]);

  async function handleApply(templateId) {
    setApplying(templateId);
    setError(null);
    try {
      const res = await api.post(`/api/incidents/${incidentId}/apply-template/`, { template_id: templateId });
      onApplied(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to apply template.');
    } finally {
      setApplying(null);
    }
  }

  if (!subjectId) return null;
  if (loading)    return <p className="text-xs text-muted-foreground">Loading templates…</p>;
  if (templates.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Suggested templates
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {templates.map(t => (
          <button
            key={t.id}
            onClick={() => handleApply(t.id)}
            disabled={applying === t.id}
            aria-label={`Apply ${t.name}`}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {applying === t.id ? 'Applying…' : t.name}
            <span className="ml-1 text-muted-foreground">({t.items.length} steps)</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── IncidentTasks ─────────────────────────────────────────────────────────────

export default function IncidentTasks({ incidentId, subjectId, refreshKey }) {
  const { user } = useAuth();
  const [tasks, setTasks]               = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);

  const loadTasks = useCallback(() => {
    setLoading(true);
    api.get(`/api/incidents/${incidentId}/tasks/`)
      .then(res => setTasks(res.data))
      .catch(() => setError('Failed to load tasks.'))
      .finally(() => setLoading(false));
  }, [incidentId]);

  useEffect(() => { loadTasks(); }, [loadTasks, refreshKey]);

  function handleTaskUpdate(updated) {
    setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
  }

  function handleTaskAdded(task) {
    setTasks(prev => [...prev, task]);
  }

  function handleTemplateApplied(newTasks) {
    setTasks(newTasks);
  }

  // Group by template name (null → "Ad-hoc")
  const groups = {};
  for (const task of tasks) {
    const key = task.template_name ?? 'Ad-hoc';
    if (!groups[key]) groups[key] = [];
    groups[key].push(task);
  }

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-foreground">Tasks</h2>

      <TemplatePicker
        incidentId={incidentId}
        subjectId={subjectId}
        onApplied={handleTemplateApplied}
      />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : tasks.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tasks yet.</p>
      ) : (
        <div className="space-y-4">
          {Object.entries(groups).map(([groupName, groupTasks]) => (
            <TaskGroup
              key={groupName}
              groupName={groupName}
              tasks={groupTasks}
              onSelect={setSelectedTask}
            />
          ))}
        </div>
      )}

      <AddAdHocForm incidentId={incidentId} onAdded={handleTaskAdded} />

      {selectedTask && (
        <TaskModal
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onUpdate={handleTaskUpdate}
          currentUserId={user?.id}
          isStaff={user?.is_staff ?? false}
        />
      )}
    </div>
  );
}
