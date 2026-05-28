import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/axios';

function ItemRow({ item, templateId, onUpdate, onDelete, automations }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description || '');
  const [order, setOrder] = useState(item.display_order);
  const [automationId, setAutomationId] = useState(item.automation ?? '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      const res = await api.patch(`/api/task-templates/${templateId}/items/${item.id}/`, {
        title, description, display_order: Number(order),
        automation: automationId === '' ? null : Number(automationId),
      });
      onUpdate(res.data);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    await api.delete(`/api/task-templates/${templateId}/items/${item.id}/`);
    onDelete(item.id);
  }

  if (editing) {
    return (
      <tr className="border-b border-border bg-accent/30">
        <td className="px-3 py-2">
          <input
            value={order}
            onChange={e => setOrder(e.target.value)}
            type="number"
            className="w-16 rounded border border-border bg-background px-2 py-1 text-sm"
          />
        </td>
        <td className="px-3 py-2" colSpan={2}>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
          />
          <input
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Description"
            className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm"
          />
          <select
            value={automationId}
            onChange={e => setAutomationId(e.target.value)}
            disabled={saving}
            className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
          >
            <option value="">No automation</option>
            {(automations ?? []).map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={saving} className="text-xs font-medium text-primary hover:underline disabled:opacity-50">
              Save
            </button>
            <button onClick={() => setEditing(false)} className="text-xs text-muted-foreground hover:underline">
              Cancel
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/20">
      <td className="px-3 py-2 text-xs text-muted-foreground w-12">{item.display_order}</td>
      <td className="px-3 py-2 text-sm font-medium text-foreground">{item.title}</td>
      <td className="px-3 py-2 text-sm text-muted-foreground max-w-xs truncate">{item.description || '—'}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {item.automation_name
          ? <span className="inline-flex items-center rounded-full bg-purple-100 px-1.5 py-0.5 text-xs text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">{item.automation_name}</span>
          : '—'}
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-2">
          <button onClick={() => setEditing(true)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
          <button onClick={handleDelete} className="text-xs text-red-600 hover:underline">Delete</button>
        </div>
      </td>
    </tr>
  );
}

function TemplateEditor({ template, onClose, onTemplateUpdate }) {
  const [items, setItems] = useState(template.items || []);
  const [automations, setAutomations] = useState([]);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newAutomation, setNewAutomation] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

  useEffect(() => {
    api.get('/api/automations/').then(res => setAutomations(res.data)).catch(() => {});
  }, []);

  async function handleAddItem(e) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      const nextOrder = items.length > 0 ? Math.max(...items.map(i => i.display_order)) + 1 : 1;
      const res = await api.post(`/api/task-templates/${template.id}/items/`, {
        title: newTitle.trim(),
        description: newDesc.trim(),
        display_order: nextOrder,
        automation: newAutomation === '' ? null : Number(newAutomation),
      });
      setItems(prev => [...prev, res.data].sort((a, b) => a.display_order - b.display_order));
      setNewTitle('');
      setNewDesc('');
      setNewAutomation('');
    } catch (err) {
      setAddError(err.response?.data?.title?.[0] || 'Failed to add item.');
    } finally {
      setAdding(false);
    }
  }

  function handleItemUpdate(updated) {
    setItems(prev => prev.map(i => i.id === updated.id ? updated : i).sort((a, b) => a.display_order - b.display_order));
  }

  function handleItemDelete(id) {
    setItems(prev => prev.filter(i => i.id !== id));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 pt-12 pb-12">
      <div className="w-full max-w-3xl rounded-lg border border-border bg-card p-6 shadow-lg space-y-5 mx-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">{template.name}</h2>
            <p className="text-xs text-muted-foreground">{template.subject_name}</p>
          </div>
          <button onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground">✕</button>
        </div>

        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground w-12">#</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Title</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Description</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Automation</th>
                <th className="px-3 py-2 w-20" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-sm text-muted-foreground">No items yet.</td></tr>
              ) : (
                items.map(item => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    templateId={template.id}
                    onUpdate={handleItemUpdate}
                    onDelete={handleItemDelete}
                    automations={automations}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <form onSubmit={handleAddItem} className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Add item</p>
          <div className="flex gap-2 flex-wrap">
            <input
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              placeholder="Title"
              disabled={adding}
              className="flex-1 min-w-32 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <input
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              disabled={adding}
              className="flex-1 min-w-32 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <select
              value={newAutomation}
              onChange={e => setNewAutomation(e.target.value)}
              disabled={adding}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            >
              <option value="">No automation</option>
              {automations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <button
              type="submit"
              disabled={adding || !newTitle.trim()}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              Add
            </button>
          </div>
          {addError && <p className="text-sm text-red-600">{addError}</p>}
        </form>
      </div>
    </div>
  );
}

function TemplateRow({ template, onArchive, onEdit }) {
  const [archiving, setArchiving] = useState(false);

  async function handleArchive() {
    setArchiving(true);
    try {
      await onArchive(template);
    } finally {
      setArchiving(false);
    }
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
      <td className="px-4 py-3 font-medium text-foreground">{template.name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{template.subject_name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">{template.description || '—'}</td>
      <td className="px-4 py-3">
        {template.is_auto_apply ? (
          <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">Auto-apply</span>
        ) : (
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">Manual</span>
        )}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${template.archived ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'}`}>
          {template.archived ? 'Archived' : 'Active'}
        </span>
      </td>
      <td className="px-4 py-3 text-center text-xs text-muted-foreground">{template.items?.length ?? 0}</td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <button onClick={() => onEdit(template)} className="rounded-md px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors">
            Edit items
          </button>
          <button
            onClick={handleArchive}
            disabled={archiving}
            className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {template.archived ? 'Unarchive' : 'Archive'}
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function TaskTemplatesAdmin() {
  const [templates, setTemplates] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);

  const [name, setName] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [description, setDescription] = useState('');
  const [isAutoApply, setIsAutoApply] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    Promise.all([api.get('/api/task-templates/'), api.get('/api/subjects/')])
      .then(([tRes, sRes]) => {
        setTemplates(tRes.data);
        setSubjects(sRes.data.filter(s => !s.archived));
      })
      .catch(() => setError('Failed to load data.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim() || !subjectId) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post('/api/task-templates/', {
        name: name.trim(),
        subject: Number(subjectId),
        description: description.trim(),
        is_auto_apply: isAutoApply,
      });
      setTemplates(prev => [...prev, res.data]);
      setName('');
      setSubjectId('');
      setDescription('');
      setIsAutoApply(false);
    } catch (err) {
      setFormError(err.response?.data?.name?.[0] || err.response?.data?.detail || 'Failed to create template.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleArchive(template) {
    try {
      if (template.archived) {
        const res = await api.patch(`/api/task-templates/${template.id}/`, { archived: false });
        setTemplates(prev => prev.map(t => t.id === template.id ? res.data : t));
      } else {
        await api.delete(`/api/task-templates/${template.id}/`);
        setTemplates(prev => prev.map(t => t.id === template.id ? { ...t, archived: true } : t));
      }
    } catch {
      setError('Failed to update template.');
    }
  }

  return (
    <div className="space-y-6 p-6">
      {editing && (
        <TemplateEditor
          template={editing}
          onClose={() => setEditing(null)}
          onTemplateUpdate={updated => setTemplates(prev => prev.map(t => t.id === updated.id ? updated : t))}
        />
      )}

      <h1 className="text-2xl font-semibold text-foreground">Task Templates</h1>

      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-base font-semibold text-foreground">Create Template</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Template name"
              disabled={submitting}
              className="col-span-2 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <select
              value={subjectId}
              onChange={e => setSubjectId(e.target.value)}
              disabled={submitting}
              aria-label="Subject"
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            >
              <option value="">Select subject…</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={isAutoApply}
                onChange={e => setIsAutoApply(e.target.checked)}
                disabled={submitting}
                className="rounded"
              />
              Auto-apply
            </label>
          </div>
          <div className="flex gap-3">
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Description (optional)"
              disabled={submitting}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={submitting || !name.trim() || !subjectId}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
          {formError && <p className="text-sm text-red-600">{formError}</p>}
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-max">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Subject</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Apply</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">Items</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
            ) : templates.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No templates.</td></tr>
            ) : (
              templates.map(t => (
                <TemplateRow key={t.id} template={t} onArchive={handleArchive} onEdit={setEditing} />
              ))
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
