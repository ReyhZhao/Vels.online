import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

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
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editContact, setEditContact] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    api.get('/api/contacts/')
      .then(res => setContacts(res.data))
      .catch(() => setError('Failed to load contacts.'))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <div className="space-y-4 p-6">
      <CreateContactModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        orgSlug={selectedOrg?.slug}
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

      <div>
        <input
          type="search"
          placeholder="Search contacts…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-64"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-max">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Department</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Job Title</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  {search ? 'No contacts match your search.' : 'No contacts yet.'}
                </td>
              </tr>
            ) : filtered.map(contact => (
              <tr key={contact.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">
                  <Link to={`/contacts/${contact.id}`} className="hover:underline">{contact.name}</Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{contact.email}</td>
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
    </div>
  );
}
