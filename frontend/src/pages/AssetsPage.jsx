import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

function CreateAssetModal({ open, onClose, orgSlug, onCreated }) {
  const [form, setForm] = useState({ name: '', agent_name: '', ip_address: '' });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ name: '', agent_name: '', ip_address: '' });
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
      const res = await api.post('/api/assets/', {
        kind: 'host',
        organization: orgSlug,
        name: form.name,
        agent_name: form.agent_name,
        ip_address: form.ip_address || undefined,
      });
      onCreated(res.data);
      onClose();
    } catch (err) {
      const data = err.response?.data;
      setError(data?.detail || data?.agent_name?.[0] || data?.name?.[0] || 'Failed to create asset.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">New Host Asset</h2>
        <form onSubmit={submit} className="space-y-3">
          {[
            { label: 'Name', field: 'name', required: true, type: 'text', placeholder: 'e.g. LAPTOP-0042' },
            { label: 'Agent Name', field: 'agent_name', required: true, type: 'text', placeholder: 'Wazuh agent name' },
            { label: 'IP Address', field: 'ip_address', required: false, type: 'text', placeholder: 'Optional' },
          ].map(({ label, field, required, type, placeholder }) => (
            <div key={field}>
              <label className="block text-sm font-medium text-foreground mb-1" htmlFor={`new-${field}`}>
                {label}{required && ' *'}
              </label>
              <input
                id={`new-${field}`}
                type={type}
                required={required}
                placeholder={placeholder}
                value={form[field]}
                onChange={e => set(field, e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
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

export default function AssetsPage() {
  const { selectedOrg } = useOrganization();
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    const params = selectedOrg ? { org: selectedOrg.slug } : {};
    api.get('/api/assets/', { params })
      .then(res => setAssets(res.data.results || res.data))
      .catch(() => setError('Failed to load assets.'))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  const filtered = assets.filter(a =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    (a.agent_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (a.ip_address || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4 p-6">
      <CreateAssetModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        orgSlug={selectedOrg?.slug}
        onCreated={asset => setAssets(prev => [...prev, asset].sort((a, b) => a.name.localeCompare(b.name)))}
      />

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Assets</h1>
        <button
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          New Asset
        </button>
      </div>

      <div>
        <input
          type="search"
          placeholder="Search assets…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-64"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Kind</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP Address</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  {search ? 'No assets match your search.' : 'No assets yet.'}
                </td>
              </tr>
            ) : filtered.map(asset => (
              <tr key={asset.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">
                  <Link to={`/assets/${asset.id}`} className="hover:underline">{asset.name}</Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground capitalize">{asset.kind}</td>
                <td className="px-4 py-3 text-muted-foreground">{asset.agent_name || '—'}</td>
                <td className="px-4 py-3 text-muted-foreground">{asset.ip_address || '—'}</td>
                <td className="px-4 py-3">
                  {asset.is_active === false ? (
                    <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-muted-foreground">inactive</span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs text-green-700 dark:text-green-400">active</span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground text-xs">
                  {asset.last_seen_at ? new Date(asset.last_seen_at).toLocaleString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
