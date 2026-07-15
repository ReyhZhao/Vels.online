import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useAuth } from '../context/AuthContext';

function CreateContactModal({ open, onClose, orgSlug, onCreated }) {
  const [form, setForm] = useState({ name: '', email: '', job_title: '', department: '' });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ name: '', email: '', job_title: '', department: '' });
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.post('/api/contacts/', { org: orgSlug, ...form });
      onCreated(res.data);
      onClose();
    } catch (err) {
      const data = err.response?.data;
      setError(data?.email?.[0] || data?.detail || 'Failed to create contact.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">New Contact</h2>
        <form onSubmit={submit} className="space-y-3">
          {[
            { label: 'Name', field: 'name', required: true, type: 'text' },
            { label: 'Email', field: 'email', required: true, type: 'email' },
            { label: 'Job Title', field: 'job_title', required: false, type: 'text' },
            { label: 'Department', field: 'department', required: false, type: 'text' },
          ].map(({ label, field, required, type }) => (
            <div key={field}>
              <label className="block text-sm font-medium text-foreground mb-1" htmlFor={`new-${field}`}>
                {label}{required && ' *'}
              </label>
              <input
                id={`new-${field}`}
                type={type}
                required={required}
                value={form[field]}
                onChange={e => set(field, e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          ))}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={saving}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {saving ? 'Saving…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditContactModal({ contact, open, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', email: '', job_title: '', department: '' });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && contact) {
      setForm({ name: contact.name, email: contact.email, job_title: contact.job_title || '', department: contact.department || '' });
      setError(null);
    }
  }, [open, contact]);

  if (!open) return null;

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.patch(`/api/contacts/${contact.id}/`, form);
      onSaved(res.data);
      onClose();
    } catch (err) {
      const data = err.response?.data;
      setError(data?.email?.[0] || data?.detail || 'Failed to save contact.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Edit Contact</h2>
        <form onSubmit={submit} className="space-y-3">
          {[
            { label: 'Name', field: 'name', required: true, type: 'text' },
            { label: 'Email', field: 'email', required: true, type: 'email' },
            { label: 'Job Title', field: 'job_title', required: false, type: 'text' },
            { label: 'Department', field: 'department', required: false, type: 'text' },
          ].map(({ label, field, required, type }) => (
            <div key={field}>
              <label className="block text-sm font-medium text-foreground mb-1" htmlFor={`edit-${field}`}>
                {label}{required && ' *'}
              </label>
              <input
                id={`edit-${field}`}
                type={type}
                required={required}
                value={form[field]}
                onChange={e => set(field, e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          ))}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={saving}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ContactsPage() {
  const { selectedOrg } = useOrganization();
  const { user } = useAuth();
  const isStaff = !!user?.is_staff;
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editContact, setEditContact] = useState(null);
  const [search, setSearch] = useState('');
  // Scope for the list + the create target: 'current' (selected tenant),
  // 'infra' (the Shared Infrastructure pseudo-org, staff only — ADR-0017),
  // or 'all' (every org, staff only). Infra stays out of the global org
  // switcher, so this page fetches it separately with include_infrastructure.
  const [scope, setScope] = useState('current');
  const [infraOrg, setInfraOrg] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const showOrgColumn = scope === 'all';
  const createOrgSlug = scope === 'infra' ? infraOrg?.slug : selectedOrg?.slug;

  useEffect(() => {
    if (!isStaff) return;
    api.get('/api/security/organizations/', { params: { include_infrastructure: 1 } })
      .then(res => setInfraOrg(res.data.find(o => o.is_infrastructure) ?? null))
      .catch(() => setInfraOrg(null));
  }, [isStaff]);

  function setSort(key) {
    if (sortKey === key) {
      setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortOrder('asc');
    }
  }

  useEffect(() => {
    setLoading(true);
    setSelected(new Set());
    let orgSlug = null;
    if (scope === 'current') orgSlug = selectedOrg?.slug ?? null;
    else if (scope === 'infra') orgSlug = infraOrg?.slug ?? null;
    const params = orgSlug ? { org: orgSlug } : {};
    api.get('/api/contacts/', { params })
      .then(res => setContacts(res.data))
      .catch(() => setError('Failed to load contacts.'))
      .finally(() => setLoading(false));
  }, [scope, selectedOrg?.slug, infraOrg?.slug]);

  async function handleDelete(contact) {
    if (!confirm(`Delete contact "${contact.name}"?`)) return;
    try {
      await api.delete(`/api/contacts/${contact.id}/`);
      setContacts(prev => prev.filter(c => c.id !== contact.id));
    } catch {
      setError('Failed to delete contact.');
    }
  }

  const filtered = contacts.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.email.toLowerCase().includes(search.toLowerCase()) ||
    (c.department || '').toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    const dir = sortOrder === 'asc' ? 1 : -1;
    const av = (a[sortKey] || '').toString().toLowerCase();
    const bv = (b[sortKey] || '').toString().toLowerCase();
    return av.localeCompare(bv) * dir;
  });

  const allSelected = sorted.length > 0 && sorted.every(c => selected.has(c.id));

  function toggleAll() {
    setSelected(prev => {
      const next = new Set(prev);
      if (allSelected) sorted.forEach(c => next.delete(c.id));
      else sorted.forEach(c => next.add(c.id));
      return next;
    });
  }

  function toggleOne(id) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleBulkDelete() {
    const ids = [...selected];
    if (!confirm(`Delete ${ids.length} contact${ids.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
    for (const id of ids) {
      try {
        await api.delete(`/api/contacts/${id}/`);
        setContacts(prev => prev.filter(c => c.id !== id));
      } catch {
        setError('Failed to delete one or more contacts.');
      }
    }
    setSelected(new Set());
  }

  const colSpan = showOrgColumn ? 7 : 6;

  return (
    <div className="space-y-4 p-6">
      <CreateContactModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        orgSlug={createOrgSlug}
        onCreated={contact => setContacts(prev => [...prev, contact].sort((a, b) => a.name.localeCompare(b.name)))}
      />
      <EditContactModal
        contact={editContact}
        open={!!editContact}
        onClose={() => setEditContact(null)}
        onSaved={updated => {
          setContacts(prev => prev.map(c => c.id === updated.id ? updated : c).sort((a, b) => a.name.localeCompare(b.name)));
          setEditContact(null);
        }}
      />

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Contacts</h1>
        <button
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          New Contact
        </button>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="search"
          placeholder="Search contacts…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-64"
        />
        <div className="inline-flex rounded-md border border-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setScope('current')}
            className={`px-3 py-1.5 font-medium transition-colors ${scope === 'current' ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-accent'}`}
          >
            {selectedOrg ? selectedOrg.name : 'Current org'}
          </button>
          {isStaff && infraOrg && (
            <button
              type="button"
              onClick={() => setScope('infra')}
              className={`border-l border-border px-3 py-1.5 font-medium transition-colors ${scope === 'infra' ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-accent'}`}
            >
              {infraOrg.name}
            </button>
          )}
          <button
            type="button"
            onClick={() => setScope('all')}
            className={`border-l border-border px-3 py-1.5 font-medium transition-colors ${scope === 'all' ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-accent'}`}
          >
            All contacts
          </button>
        </div>
        {selected.size > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-1.5">
            <span className="text-sm text-foreground font-medium">{selected.size} selected</span>
            <button
              onClick={handleBulkDelete}
              className="rounded-md px-3 py-1 text-xs font-medium text-red-600 hover:bg-accent transition-colors"
            >
              Delete selected
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : sorted.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {search ? 'No contacts match your search.' : 'No contacts yet.'}
          </p>
        ) : sorted.map(contact => (
          <div key={contact.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-1">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(contact.id)}
                onChange={() => toggleOne(contact.id)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                aria-label={`Select ${contact.name}`}
              />
              <Link to={`/contacts/${contact.id}`} className="font-medium text-foreground hover:underline">{contact.name}</Link>
            </div>
            <p className="text-xs text-muted-foreground">{contact.email}</p>
            <p className="text-xs text-muted-foreground">
              {[contact.job_title, contact.department].filter(Boolean).join(' · ') || '—'}
              {showOrgColumn && contact.org_name ? ` · ${contact.org_name}` : ''}
            </p>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setEditContact(contact)} className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors">Edit</button>
              <button onClick={() => handleDelete(contact)} className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-accent transition-colors">Delete</button>
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
                  checked={allSelected}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('name')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Name">
                  Name
                  {sortKey === 'name' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
              {showOrgColumn && (
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organisation</th>
              )}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('department')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Department">
                  Department
                  {sortKey === 'department' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Job Title</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={colSpan} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-4 py-8 text-center text-muted-foreground">
                  {search ? 'No contacts match your search.' : 'No contacts yet.'}
                </td>
              </tr>
            ) : sorted.map(contact => (
              <tr key={contact.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                <td className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={selected.has(contact.id)}
                    onChange={() => toggleOne(contact.id)}
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    aria-label={`Select ${contact.name}`}
                  />
                </td>
                <td className="px-4 py-3 font-medium text-foreground">
                  <Link to={`/contacts/${contact.id}`} className="hover:underline">{contact.name}</Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{contact.email}</td>
                {showOrgColumn && (
                  <td className="px-4 py-3 text-muted-foreground">{contact.org_name || '—'}</td>
                )}
                <td className="px-4 py-3 text-muted-foreground">{contact.department || '—'}</td>
                <td className="px-4 py-3 text-muted-foreground">{contact.job_title || '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditContact(contact)}
                      className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(contact)}
                      className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-accent transition-colors"
                    >
                      Delete
                    </button>
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
