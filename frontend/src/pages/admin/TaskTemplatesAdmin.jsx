import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import api from '@/lib/axios';

const ITEM_KIND_LABELS = {
  manual: 'Manual',
  automation: 'Automation',
  wazuh: 'Wazuh Response',
  contact: 'Contact',
};

const CONTACT_ROLE_OPTIONS = [
  { value: 'notified', label: 'Notify' },
  { value: 'questioned', label: 'Question (reply-enabled)' },
  { value: 'update', label: 'Update' },
];

const CONTACT_PLACEHOLDERS = [
  { token: '{{ display_id }}', label: 'Incident display id (e.g. INC-2026-0042)' },
  { token: '{{ title }}', label: 'Incident title' },
  { token: '{{ severity }}', label: 'Incident severity' },
  { token: '{{ description }}', label: 'Incident description' },
  { token: '{{ org_name }}', label: 'Organisation name' },
];

function ContactPlaceholderHelp() {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
      <p className="font-medium text-foreground">Available placeholders</p>
      <p className="mt-0.5">Filled in from the incident when the message is sent.</p>
      <ul className="mt-1.5 space-y-0.5">
        {CONTACT_PLACEHOLDERS.map(p => (
          <li key={p.token} className="flex items-baseline gap-2">
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-foreground whitespace-nowrap">{p.token}</code>
            <span>{p.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemRow({ item, templateId, onUpdate, onDelete, automations, wazuhResponses }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description || '');
  const [order, setOrder] = useState(item.display_order);
  const [itemKind, setItemKind] = useState(
    item.is_contact_task ? 'contact' : item.wazuh_response ? 'wazuh' : item.automation ? 'automation' : 'manual'
  );
  const [automationId, setAutomationId] = useState(item.automation ?? '');
  const [wazuhResponseId, setWazuhResponseId] = useState(item.wazuh_response ?? '');
  const [contactRole, setContactRole] = useState(item.contact_role || 'notified');
  const [contactBody, setContactBody] = useState(item.contact_body || '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      const res = await api.patch(`/api/task-templates/${templateId}/items/${item.id}/`, {
        title, description, display_order: Number(order),
        automation: itemKind === 'automation' && automationId !== '' ? Number(automationId) : null,
        wazuh_response: itemKind === 'wazuh' && wazuhResponseId !== '' ? Number(wazuhResponseId) : null,
        is_contact_task: itemKind === 'contact',
        contact_role: itemKind === 'contact' ? contactRole : '',
        contact_body: itemKind === 'contact' ? contactBody : '',
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
          <div className="mt-1 flex gap-1">
            {['manual', 'automation', 'wazuh', 'contact'].map(k => (
              <button
                key={k}
                type="button"
                onClick={() => setItemKind(k)}
                className={`rounded px-2 py-0.5 text-xs font-medium border transition-colors ${itemKind === k ? 'bg-primary text-primary-foreground border-primary' : 'bg-background text-foreground border-border hover:bg-accent'}`}
              >
                {ITEM_KIND_LABELS[k]}
              </button>
            ))}
          </div>
          {itemKind === 'contact' && (
            <div className="mt-1 space-y-1">
              <select
                value={contactRole}
                onChange={e => setContactRole(e.target.value)}
                disabled={saving}
                aria-label="Contact role"
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
              >
                {CONTACT_ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <textarea
                value={contactBody}
                onChange={e => setContactBody(e.target.value)}
                disabled={saving}
                rows={3}
                placeholder="Message body"
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
              />
              <ContactPlaceholderHelp />
            </div>
          )}
          {itemKind === 'automation' && (
            <select
              value={automationId}
              onChange={e => setAutomationId(e.target.value)}
              disabled={saving}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
            >
              <option value="">Select automation…</option>
              {(automations ?? []).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          )}
          {itemKind === 'wazuh' && (
            <select
              value={wazuhResponseId}
              onChange={e => setWazuhResponseId(e.target.value)}
              disabled={saving}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
            >
              <option value="">Select Wazuh response…</option>
              {(wazuhResponses ?? []).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
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
          : item.wazuh_response_name
          ? <span className="inline-flex items-center rounded-full bg-orange-100 px-1.5 py-0.5 text-xs text-orange-800 dark:bg-orange-900/30 dark:text-orange-400">{item.wazuh_response_name}</span>
          : item.is_contact_task
          ? <span className="inline-flex items-center rounded-full bg-teal-100 px-1.5 py-0.5 text-xs text-teal-800 dark:bg-teal-900/30 dark:text-teal-400">Contact</span>
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
  const [wazuhResponses, setWazuhResponses] = useState([]);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newItemKind, setNewItemKind] = useState('manual');
  const [newAutomation, setNewAutomation] = useState('');
  const [newWazuhResponse, setNewWazuhResponse] = useState('');
  const [newContactRole, setNewContactRole] = useState('notified');
  const [newContactBody, setNewContactBody] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

  useEffect(() => {
    api.get('/api/automations/').then(res => setAutomations(res.data)).catch(() => {});
    api.get('/api/wazuh-responses/').then(res => setWazuhResponses(res.data)).catch(() => {});
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
        automation: newItemKind === 'automation' && newAutomation !== '' ? Number(newAutomation) : null,
        wazuh_response: newItemKind === 'wazuh' && newWazuhResponse !== '' ? Number(newWazuhResponse) : null,
        is_contact_task: newItemKind === 'contact',
        contact_role: newItemKind === 'contact' ? newContactRole : '',
        contact_body: newItemKind === 'contact' ? newContactBody : '',
      });
      setItems(prev => [...prev, res.data].sort((a, b) => a.display_order - b.display_order));
      setNewTitle('');
      setNewDesc('');
      setNewItemKind('manual');
      setNewAutomation('');
      setNewWazuhResponse('');
      setNewContactRole('notified');
      setNewContactBody('');
    } catch (err) {
      setAddError(err.response?.data?.contact_body?.[0] || err.response?.data?.title?.[0] || err.response?.data?.detail || 'Failed to add item.');
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
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Action</th>
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
                    wazuhResponses={wazuhResponses}
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
          </div>
          <div className="flex gap-2 flex-wrap items-center">
            <div className="flex items-center rounded-md border border-border bg-background text-sm overflow-hidden">
              {['manual', 'automation', 'wazuh', 'contact'].map(k => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setNewItemKind(k)}
                  className={`px-3 py-1.5 font-medium transition-colors ${newItemKind === k ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-accent'}`}
                >
                  {ITEM_KIND_LABELS[k]}
                </button>
              ))}
            </div>
            {newItemKind === 'automation' && (
              <select
                value={newAutomation}
                onChange={e => setNewAutomation(e.target.value)}
                disabled={adding}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                <option value="">Select automation…</option>
                {automations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            )}
            {newItemKind === 'wazuh' && (
              <select
                value={newWazuhResponse}
                onChange={e => setNewWazuhResponse(e.target.value)}
                disabled={adding}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                <option value="">Select Wazuh response…</option>
                {wazuhResponses.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            )}
            <button
              type="submit"
              disabled={adding || !newTitle.trim() || (newItemKind === 'contact' && !newContactBody.trim())}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              Add
            </button>
          </div>
          {newItemKind === 'contact' && (
            <div className="space-y-1">
              <select
                value={newContactRole}
                onChange={e => setNewContactRole(e.target.value)}
                disabled={adding}
                aria-label="Contact role"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                {CONTACT_ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <textarea
                value={newContactBody}
                onChange={e => setNewContactBody(e.target.value)}
                disabled={adding}
                rows={3}
                placeholder="Message body"
                aria-label="Contact message body"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              />
              <ContactPlaceholderHelp />
            </div>
          )}
          {addError && <p className="text-sm text-red-600">{addError}</p>}
        </form>
      </div>
    </div>
  );
}

function TemplateMetaEditor({ template, onClose, onSave }) {
  const [name, setName] = useState(template.name);
  const [description, setDescription] = useState(template.description || '');
  const [isAutoApply, setIsAutoApply] = useState(template.is_auto_apply);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.patch(`/api/task-templates/${template.id}/`, {
        name: name.trim(),
        description: description.trim(),
        is_auto_apply: isAutoApply,
      });
      onSave(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.name?.[0] || err.response?.data?.detail || 'Failed to save template.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4 mx-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Edit Template</h2>
          <button onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={saving}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Description</label>
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Description (optional)"
              disabled={saving}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={isAutoApply}
              onChange={e => setIsAutoApply(e.target.checked)}
              disabled={saving}
              className="rounded"
            />
            Auto-apply
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const SORT_COLUMNS = {
  name:    { label: 'Name',    defaultOrder: 'asc' },
  subject: { label: 'Subject', defaultOrder: 'asc' },
  status:  { label: 'Status',  defaultOrder: 'asc' },
};

function ApplyBadge({ autoApply }) {
  return autoApply ? (
    <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">Auto-apply</span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">Manual</span>
  );
}

function StatusBadge({ archived }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${archived ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'}`}>
      {archived ? 'Archived' : 'Active'}
    </span>
  );
}

function KebabMenu({ label, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block text-left">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={label}
        className="rounded-md px-2 py-1 text-base leading-none text-muted-foreground hover:bg-accent transition-colors"
      >
        ⋮
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-40 rounded-md border border-border bg-card py-1 shadow-lg"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function MenuItem({ onClick, children, danger }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={`block w-full px-3 py-1.5 text-left text-xs font-medium hover:bg-accent transition-colors ${danger ? 'text-red-600' : 'text-foreground'}`}
    >
      {children}
    </button>
  );
}

export default function TaskTemplatesAdmin() {
  const [templates, setTemplates] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [editingMeta, setEditingMeta] = useState(null);

  const [name, setName] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [description, setDescription] = useState('');
  const [isAutoApply, setIsAutoApply] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [subjectFilter, setSubjectFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

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

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder(SORT_COLUMNS[key]?.defaultOrder ?? 'asc');
    }
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = templates.filter(t => {
      if (statusFilter === 'active' && t.archived) return false;
      if (statusFilter === 'archived' && !t.archived) return false;
      if (subjectFilter !== 'all' && String(t.subject) !== String(subjectFilter)) return false;
      if (!q) return true;
      return (
        (t.name || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q)
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      if (sortKey === 'status') return ((a.archived ? 1 : 0) - (b.archived ? 1 : 0)) * dir;
      const key = sortKey === 'subject' ? 'subject_name' : 'name';
      return (a[key] || '').toString().toLowerCase()
        .localeCompare((b[key] || '').toString().toLowerCase()) * dir;
    });
    return rows;
  }, [templates, search, statusFilter, subjectFilter, sortKey, sortOrder]);

  const visibleIds = visible.map(t => t.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.has(id));
  const someVisibleSelected = visibleIds.some(id => selectedIds.has(id));

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allVisibleSelected) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.delete(id));
        return next;
      });
    } else {
      setSelectedIds(prev => new Set([...prev, ...visibleIds]));
    }
  }

  async function handleBulk(archived) {
    setBulkBusy(true);
    const targets = visible.filter(t => selectedIds.has(t.id) && t.archived !== archived);
    for (const t of targets) {
      await handleArchive(t);
    }
    setSelectedIds(new Set());
    setBulkBusy(false);
  }

  function SortHeader({ field, className = '' }) {
    return (
      <th className={`px-4 py-3 text-left font-medium text-muted-foreground ${className}`}>
        <button
          onClick={() => setSort(field)}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
        >
          {SORT_COLUMNS[field].label}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  function RowMenu({ template }) {
    return (
      <KebabMenu label={`Actions for ${template.name}`}>
        <MenuItem onClick={() => setEditingMeta(template)}>Edit</MenuItem>
        <MenuItem onClick={() => setEditing(template)}>Edit items</MenuItem>
        <MenuItem onClick={() => handleArchive(template)}>
          {template.archived ? 'Unarchive' : 'Archive'}
        </MenuItem>
      </KebabMenu>
    );
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
      {editingMeta && (
        <TemplateMetaEditor
          template={editingMeta}
          onClose={() => setEditingMeta(null)}
          onSave={updated => setTemplates(prev => prev.map(t => t.id === updated.id ? updated : t))}
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

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search templates…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search templates"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
        {subjects.length > 0 && (
          <select
            value={subjectFilter}
            onChange={e => setSubjectFilter(e.target.value)}
            aria-label="Subject filter"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All subjects</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
      </div>

      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card px-4 py-2">
          <span className="text-sm font-medium text-foreground">{selectedIds.size} selected</span>
          <button
            onClick={() => handleBulk(true)}
            disabled={bulkBusy}
            aria-label="Archive selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Archive
          </button>
          <button
            onClick={() => handleBulk(false)}
            disabled={bulkBusy}
            aria-label="Unarchive selected"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Unarchive
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        </div>
      )}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No templates.</p>
        ) : visible.map(t => (
          <div key={t.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.has(t.id)}
                  onChange={() => toggleSelect(t.id)}
                  aria-label={`Select ${t.name}`}
                  className="mt-1 h-4 w-4 rounded border-border"
                />
                <div>
                  <p className="font-medium text-foreground leading-snug">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.subject_name}</p>
                </div>
              </div>
              <RowMenu template={t} />
            </div>
            {t.description && <p className="text-xs text-muted-foreground">{t.description}</p>}
            <div className="flex flex-wrap items-center gap-2">
              <ApplyBadge autoApply={t.is_auto_apply} />
              <StatusBadge archived={t.archived} />
              <span className="text-xs text-muted-foreground">{t.items?.length ?? 0} items</span>
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
                  aria-label="Select all"
                  checked={allVisibleSelected}
                  ref={el => { if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected; }}
                  onChange={toggleSelectAll}
                  className="rounded border-border"
                />
              </th>
              <SortHeader field="name" />
              <SortHeader field="subject" />
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Apply</th>
              <SortHeader field="status" />
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">Items</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">No templates.</td></tr>
            ) : (
              visible.map(t => (
                <tr key={t.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                  <td className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      aria-label={`Select ${t.name}`}
                      checked={selectedIds.has(t.id)}
                      onChange={() => toggleSelect(t.id)}
                      className="rounded border-border"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-foreground">{t.name}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{t.subject_name}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">{t.description || '—'}</td>
                  <td className="px-4 py-3"><ApplyBadge autoApply={t.is_auto_apply} /></td>
                  <td className="px-4 py-3"><StatusBadge archived={t.archived} /></td>
                  <td className="px-4 py-3 text-center text-xs text-muted-foreground">{t.items?.length ?? 0}</td>
                  <td className="px-4 py-3 text-right"><RowMenu template={t} /></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
