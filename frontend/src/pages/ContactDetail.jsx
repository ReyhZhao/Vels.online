import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const FIELDS = [
  { key: 'name', label: 'Name', type: 'text', required: true },
  { key: 'email', label: 'Email', type: 'email', required: true },
  { key: 'job_title', label: 'Job Title', type: 'text', required: false },
  { key: 'department', label: 'Department', type: 'text', required: false },
];

function ConfirmDeleteModal({ open, onConfirm, onCancel, loading }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Delete contact?</h2>
        <p className="text-sm text-muted-foreground">This action cannot be undone.</p>
        <div className="flex justify-end gap-3">
          <button onClick={onCancel} disabled={loading}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50">
            Cancel
          </button>
          <button onClick={onConfirm} disabled={loading}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">
            {loading ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}

function OwnedAssetsSection({ contactId, orgSlug }) {
  const [ownedAssets, setOwnedAssets] = useState([]);
  const [allAssets, setAllAssets] = useState([]);
  const [search, setSearch] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState(null);

  useEffect(() => {
    api.get(`/api/contacts/${contactId}/assets/`).then(r => setOwnedAssets(r.data)).catch(() => {});
    if (orgSlug) {
      api.get('/api/assets/', { params: { org: orgSlug } }).then(r => setAllAssets(r.data.results || r.data)).catch(() => {});
    }
  }, [contactId, orgSlug]);

  const ownedIds = new Set(ownedAssets.map(a => a.id));
  const filtered = allAssets.filter(a =>
    !ownedIds.has(a.id) &&
    (a.name.toLowerCase().includes(search.toLowerCase()) || (a.agent_name || '').toLowerCase().includes(search.toLowerCase()))
  );

  async function assign(assetId) {
    setAssigning(true);
    setAssignError(null);
    try {
      await api.post(`/api/contacts/${contactId}/assets/`, { asset_id: assetId });
      const res = await api.get(`/api/contacts/${contactId}/assets/`);
      setOwnedAssets(res.data);
      setSearch('');
    } catch (err) {
      setAssignError(err.response?.data?.detail || 'Failed to assign asset.');
    } finally {
      setAssigning(false);
    }
  }

  async function remove(assetId) {
    try {
      await api.delete(`/api/contacts/${contactId}/assets/${assetId}/`);
      setOwnedAssets(prev => prev.filter(a => a.id !== assetId));
    } catch {
      // silently ignore
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-semibold text-foreground">Owned Assets</h2>
      {ownedAssets.length === 0 ? (
        <p className="text-sm text-muted-foreground">No owned assets.</p>
      ) : (
        <ul className="divide-y divide-border">
          {ownedAssets.map(asset => (
            <li key={asset.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <span className="font-medium text-foreground">{asset.name}</span>
                <span className="ml-2 text-xs text-muted-foreground capitalize">{asset.kind}</span>
                {asset.is_active === false && (
                  <span className="ml-2 inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-muted-foreground">inactive</span>
                )}
              </div>
              <button onClick={() => remove(asset.id)} className="text-xs text-red-500 hover:text-red-700">Remove</button>
            </li>
          ))}
        </ul>
      )}
      <div className="space-y-2">
        <input
          type="search"
          placeholder="Search assets to assign…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {search && filtered.length > 0 && (
          <ul className="rounded-md border border-border bg-background divide-y divide-border max-h-48 overflow-y-auto">
            {filtered.slice(0, 10).map(asset => (
              <li key={asset.id}>
                <button
                  onClick={() => assign(asset.id)}
                  disabled={assigning}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50 text-foreground disabled:opacity-50"
                >
                  {asset.name} <span className="text-xs text-muted-foreground capitalize">({asset.kind})</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {search && filtered.length === 0 && (
          <p className="text-xs text-muted-foreground">No unassigned assets match.</p>
        )}
        {assignError && <p className="text-xs text-red-600">{assignError}</p>}
      </div>
    </div>
  );
}

export default function ContactDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();
  const [contact, setContact] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api.get(`/api/contacts/${id}/`)
      .then(res => {
        setContact(res.data);
        setForm({ name: res.data.name, email: res.data.email, job_title: res.data.job_title || '', department: res.data.department || '' });
      })
      .catch(() => setError('Contact not found.'))
      .finally(() => setLoading(false));
  }, [id]);

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.patch(`/api/contacts/${id}/`, form);
      setContact(res.data);
    } catch (err) {
      const data = err.response?.data;
      setSaveError(data?.email?.[0] || data?.detail || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await api.delete(`/api/contacts/${id}/`);
      navigate('/contacts');
    } catch {
      setDeleting(false);
      setDeleteOpen(false);
    }
  }

  if (loading) {
    return <div className="p-6 text-muted-foreground">Loading…</div>;
  }

  if (error || !contact) {
    return <div className="p-6 text-red-600">{error || 'Not found.'}</div>;
  }

  return (
    <div className="p-6 max-w-xl space-y-6">
      <ConfirmDeleteModal
        open={deleteOpen}
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">{contact.name}</h1>
        <button
          onClick={() => setDeleteOpen(true)}
          className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
        >
          Delete
        </button>
      </div>

      <form onSubmit={save} className="space-y-4 rounded-lg border border-border bg-card p-4">
        {FIELDS.map(({ key, label, type, required }) => (
          <div key={key}>
            <label className="block text-sm font-medium text-foreground mb-1" htmlFor={`field-${key}`}>
              {label}
            </label>
            <input
              id={`field-${key}`}
              type={type}
              required={required}
              value={form[key] || ''}
              onChange={e => set(key, e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        ))}
        {saveError && <p className="text-sm text-red-600">{saveError}</p>}
        <div className="flex justify-end">
          <button type="submit" disabled={saving}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>

      <OwnedAssetsSection contactId={id} orgSlug={selectedOrg?.slug} />

      <p className="text-xs text-muted-foreground">
        Created {new Date(contact.created_at).toLocaleString()}
      </p>
    </div>
  );
}
