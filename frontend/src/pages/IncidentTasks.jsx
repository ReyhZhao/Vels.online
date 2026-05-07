import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';

const TASK_STATE_LABELS = {
  new: 'New',
  in_progress: 'In Progress',
  done: 'Done',
  cancelled: 'Cancelled',
};

const TASK_STATE_CLASSES = {
  new: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  done: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

function TaskRow({ task, onUpdate }) {
  const [saving, setSaving] = useState(false);

  async function changeState(newState) {
    setSaving(true);
    try {
      const res = await api.patch(`/api/tasks/${task.id}/`, { state: newState });
      onUpdate(res.data);
    } finally {
      setSaving(false);
    }
  }

  const nextStates = ['new', 'in_progress', 'done', 'cancelled'].filter(s => s !== task.state);

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/20">
      <td className="px-3 py-2 text-xs text-muted-foreground w-8">{task.display_order}</td>
      <td className="px-3 py-2 text-sm font-medium text-foreground">{task.title}</td>
      <td className="px-3 py-2 text-sm text-muted-foreground max-w-xs truncate">{task.description || '—'}</td>
      <td className="px-3 py-2">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TASK_STATE_CLASSES[task.state] ?? ''}`}>
          {TASK_STATE_LABELS[task.state] ?? task.state}
        </span>
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-1 flex-wrap">
          {nextStates.map(s => (
            <button
              key={s}
              onClick={() => changeState(s)}
              disabled={saving}
              className="rounded px-2 py-0.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50 transition-colors"
            >
              {TASK_STATE_LABELS[s]}
            </button>
          ))}
        </div>
      </td>
    </tr>
  );
}

function TaskGroup({ groupName, tasks, onUpdate }) {
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
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Description</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">State</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(task => (
              <TaskRow key={task.id} task={task} onUpdate={onUpdate} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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

function TemplatePicker({ incidentId, subjectId, onApplied }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(null);
  const [error, setError] = useState(null);

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
  if (loading) return <p className="text-xs text-muted-foreground">Loading templates…</p>;
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

export default function IncidentTasks({ incidentId, subjectId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadTasks = useCallback(() => {
    setLoading(true);
    api.get(`/api/incidents/${incidentId}/tasks/`)
      .then(res => setTasks(res.data))
      .catch(() => setError('Failed to load tasks.'))
      .finally(() => setLoading(false));
  }, [incidentId]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  function handleTaskUpdate(updated) {
    setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
  }

  function handleTaskAdded(task) {
    setTasks(prev => [...prev, task]);
  }

  function handleTemplateApplied(newTasks) {
    setTasks(newTasks);
  }

  // Group tasks by template name (null → "Ad-hoc")
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
              onUpdate={handleTaskUpdate}
            />
          ))}
        </div>
      )}

      <AddAdHocForm incidentId={incidentId} onAdded={handleTaskAdded} />
    </div>
  );
}
