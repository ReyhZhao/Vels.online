import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const ASSET_ROLES = [
  { value: '', label: 'Unknown / unset' },
  { value: 'workstation', label: 'Workstation' },
  { value: 'server', label: 'Server' },
  { value: 'dns-server', label: 'DNS Server' },
  { value: 'domain-controller', label: 'Domain Controller' },
  { value: 'jumphost', label: 'Jumphost' },
  { value: 'firewall', label: 'Firewall' },
  { value: 'router', label: 'Router' },
  { value: 'switch', label: 'Switch' },
  { value: 'database-server', label: 'Database Server' },
  { value: 'web-server', label: 'Web Server' },
  { value: 'other', label: 'Other' },
];

function ConfirmDeleteModal({ open, onConfirm, onCancel, loading }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Delete asset?</h2>
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

function ExposuresPanel({ exposures }) {
  if (!exposures || exposures.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-base font-semibold text-foreground mb-2">Exposures</h2>
        <p className="text-sm text-muted-foreground">No exposures.</p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h2 className="text-base font-semibold text-foreground">Exposures</h2>
      <ul className="divide-y divide-border">
        {exposures.map((exp, i) => (
          <li key={i} className="flex items-center gap-3 py-2 text-sm">
            {exp.protection === 'protected' ? (
              <span className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs font-medium text-green-700 dark:text-green-400">protected</span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-orange-100 dark:bg-orange-900/30 px-2 py-0.5 text-xs font-medium text-orange-700 dark:text-orange-400">raw</span>
            )}
            {exp.kind === 'ingress_route' ? (
              <span className="text-foreground font-mono">{exp.specifics.fqdn}</span>
            ) : (
              <span className="text-foreground font-mono">
                {exp.specifics.protocol?.toUpperCase()}/{exp.specifics.port}
                {exp.specifics.public_ip && <span className="text-muted-foreground"> · {exp.specifics.public_ip}</span>}
                {exp.specifics.description && <span className="text-muted-foreground ml-1">— {exp.specifics.description}</span>}
              </span>
            )}
            <span className="ml-auto text-xs text-muted-foreground capitalize">{exp.kind.replace('_', ' ')}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NatExposureForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState({
    protocol: initial?.protocol ?? 'tcp',
    port: initial?.port ?? '',
    public_ip: initial?.public_ip ?? '',
    description: initial?.description ?? '',
  });

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSave({
      protocol: form.protocol,
      port: Number(form.port),
      public_ip: form.public_ip || null,
      description: form.description,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border border-border bg-background p-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-foreground mb-1">Protocol *</label>
          <select
            value={form.protocol}
            onChange={e => set('protocol', e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-foreground mb-1">Port *</label>
          <input
            type="number"
            required
            min="1"
            max="65535"
            value={form.port}
            onChange={e => set('port', e.target.value)}
            placeholder="443"
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-foreground mb-1">Public IP</label>
        <input
          type="text"
          value={form.public_ip}
          onChange={e => set('public_ip', e.target.value)}
          placeholder="Optional — e.g. 203.0.113.5"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-foreground mb-1">Description</label>
        <input
          type="text"
          value={form.description}
          onChange={e => set('description', e.target.value)}
          placeholder="Optional — e.g. RDP, SSH"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={saving}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50">
          Cancel
        </button>
        <button type="submit" disabled={saving || !form.port}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  );
}

function NatExposureEditor({ assetId, onExposuresChanged }) {
  const [nats, setNats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/api/assets/${assetId}/nat-exposures/`)
      .then(r => setNats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [assetId]);

  async function handleAdd(data) {
    setSaving(true);
    setError(null);
    try {
      const res = await api.post(`/api/assets/${assetId}/nat-exposures/`, data);
      setNats(prev => [...prev, res.data]);
      setAddOpen(false);
      onExposuresChanged?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add exposure.');
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit(id, data) {
    setSaving(true);
    setError(null);
    try {
      const res = await api.patch(`/api/assets/${assetId}/nat-exposures/${id}/`, data);
      setNats(prev => prev.map(n => n.id === id ? res.data : n));
      setEditingId(null);
      onExposuresChanged?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update exposure.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    setSaving(true);
    setError(null);
    try {
      await api.delete(`/api/assets/${assetId}/nat-exposures/${id}/`);
      setNats(prev => prev.filter(n => n.id !== id));
      onExposuresChanged?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete exposure.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Direct NAT Exposures</h2>
        {!addOpen && (
          <button
            type="button"
            onClick={() => { setAddOpen(true); setEditingId(null); }}
            className="rounded-md border border-border px-2 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            Add
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : nats.length === 0 && !addOpen ? (
        <p className="text-sm text-muted-foreground">No direct-NAT exposures defined.</p>
      ) : (
        <ul className="divide-y divide-border">
          {nats.map(nat => (
            <li key={nat.id} className="py-2">
              {editingId === nat.id ? (
                <NatExposureForm
                  initial={nat}
                  saving={saving}
                  onSave={data => handleEdit(nat.id, data)}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div className="flex items-center justify-between text-sm">
                  <span className="font-mono text-foreground">
                    {nat.protocol.toUpperCase()}/{nat.port}
                    {nat.public_ip && <span className="text-muted-foreground"> · {nat.public_ip}</span>}
                    {nat.description && <span className="text-muted-foreground ml-1">— {nat.description}</span>}
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => { setEditingId(nat.id); setAddOpen(false); }}
                      disabled={saving}
                      className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(nat.id)}
                      disabled={saving}
                      className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {addOpen && (
        <NatExposureForm
          saving={saving}
          onSave={handleAdd}
          onCancel={() => setAddOpen(false)}
        />
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

function OwnersSection({ assetId, assetOrgSlug }) {
  const [owners, setOwners] = useState([]);
  const [allContacts, setAllContacts] = useState([]);
  const [search, setSearch] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState(null);

  useEffect(() => {
    api.get(`/api/assets/${assetId}/owners/`).then(r => setOwners(r.data)).catch(() => {});
    api.get('/api/contacts/').then(r => setAllContacts(r.data)).catch(() => {});
  }, [assetId]);

  const ownerIds = new Set(owners.map(c => c.id));
  const filtered = allContacts.filter(c =>
    !ownerIds.has(c.id) &&
    (c.name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase()))
  );

  async function assign(contactId) {
    setAssigning(true);
    setAssignError(null);
    try {
      await api.post(`/api/assets/${assetId}/owners/`, { contact_id: contactId });
      const res = await api.get(`/api/assets/${assetId}/owners/`);
      setOwners(res.data);
      setSearch('');
    } catch (err) {
      setAssignError(err.response?.data?.detail || 'Failed to assign contact.');
    } finally {
      setAssigning(false);
    }
  }

  async function remove(contactId) {
    try {
      await api.delete(`/api/assets/${assetId}/owners/${contactId}/`);
      setOwners(prev => prev.filter(c => c.id !== contactId));
    } catch {
      // silently ignore
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-semibold text-foreground">Owners</h2>
      {owners.length === 0 ? (
        <p className="text-sm text-muted-foreground">No owners assigned.</p>
      ) : (
        <ul className="divide-y divide-border">
          {owners.map(contact => (
            <li key={contact.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <span className="font-medium text-foreground">{contact.name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{contact.email}</span>
                {contact.department && (
                  <span className="ml-2 text-xs text-muted-foreground">· {contact.department}</span>
                )}
              </div>
              <button onClick={() => remove(contact.id)} className="text-xs text-red-500 hover:text-red-700">Remove</button>
            </li>
          ))}
        </ul>
      )}
      <div className="space-y-2">
        <input
          type="search"
          placeholder="Search contacts to assign…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {search && filtered.length > 0 && (
          <ul className="rounded-md border border-border bg-background divide-y divide-border max-h-48 overflow-y-auto">
            {filtered.slice(0, 10).map(contact => (
              <li key={contact.id}>
                <button
                  onClick={() => assign(contact.id)}
                  disabled={assigning}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50 text-foreground disabled:opacity-50"
                >
                  {contact.name} <span className="text-xs text-muted-foreground">({contact.email})</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {search && filtered.length === 0 && (
          <p className="text-xs text-muted-foreground">No unassigned contacts match.</p>
        )}
        {assignError && <p className="text-xs text-red-600">{assignError}</p>}
      </div>
    </div>
  );
}

export default function AssetDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { selectedOrg } = useOrganization();
  const [asset, setAsset] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ name: '', ip_address: '', role: '' });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  function loadAsset() {
    return api.get(`/api/assets/${id}/`)
      .then(res => {
        setAsset(res.data);
        setForm({ name: res.data.name, ip_address: res.data.ip_address || '', role: res.data.role || '', is_permanent: res.data.is_permanent ?? false });
      });
  }

  useEffect(() => {
    loadAsset()
      .catch(() => setError('Asset not found.'))
      .finally(() => setLoading(false));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    const payload = { ...form, role: form.role || null };
    try {
      const res = await api.patch(`/api/assets/${id}/`, payload);
      setAsset(res.data);
    } catch (err) {
      const data = err.response?.data;
      setSaveError(data?.detail || data?.name?.[0] || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await api.delete(`/api/assets/${id}/`);
      navigate('/assets');
    } catch {
      setDeleting(false);
      setDeleteOpen(false);
    }
  }

  if (loading) {
    return <div className="p-6 text-muted-foreground">Loading…</div>;
  }

  if (error || !asset) {
    return <div className="p-6 text-red-600">{error || 'Not found.'}</div>;
  }

  const isHost = asset.kind === 'host';

  return (
    <div className="p-6 max-w-xl space-y-6">
      <ConfirmDeleteModal
        open={deleteOpen}
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-foreground">{asset.name}</h1>
          {asset.is_active === false ? (
            <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-muted-foreground">inactive</span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs text-green-700 dark:text-green-400">active</span>
          )}
          {asset.is_permanent && (
            <span className="inline-flex items-center rounded-full bg-violet-100 dark:bg-violet-900/30 px-2 py-0.5 text-xs text-violet-700 dark:text-violet-400">permanent</span>
          )}
          {asset.internet_facing && (
            <span className="inline-flex items-center rounded-full bg-orange-100 dark:bg-orange-900/30 px-2 py-0.5 text-xs text-orange-700 dark:text-orange-400">internet-facing</span>
          )}
        </div>
        <button
          onClick={() => setDeleteOpen(true)}
          className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
        >
          Delete
        </button>
      </div>

      <form onSubmit={save} className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1" htmlFor="field-name">Name</label>
          <input
            id="field-name"
            type="text"
            required
            disabled={!isHost}
            value={form.name}
            onChange={e => set('name', e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1" htmlFor="field-agent-name">Agent Name</label>
          <input
            id="field-agent-name"
            type="text"
            disabled
            value={asset.agent_name || '—'}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1" htmlFor="field-ip">IP Address</label>
          <input
            id="field-ip"
            type="text"
            disabled={!isHost}
            value={form.ip_address}
            onChange={e => set('ip_address', e.target.value)}
            placeholder="Optional"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1" htmlFor="field-role">Role</label>
          <select
            id="field-role"
            disabled={!isHost}
            value={form.role}
            onChange={e => set('role', e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          >
            {ASSET_ROLES.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        {asset.last_seen_at && (
          <p className="text-xs text-muted-foreground">
            Last seen {new Date(asset.last_seen_at).toLocaleString()}
          </p>
        )}
        <div className="flex items-center gap-3">
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              className="peer sr-only"
              checked={form.is_permanent}
              onChange={e => set('is_permanent', e.target.checked)}
            />
            <div className="h-5 w-9 rounded-full bg-border peer-checked:bg-primary transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-4" />
          </label>
          <div>
            <p className="text-sm font-medium text-foreground">Permanent</p>
            <p className="text-xs text-muted-foreground">Permanent assets are never removed by automated cleanup.</p>
          </div>
        </div>
        {saveError && <p className="text-sm text-red-600">{saveError}</p>}
        {isHost && (
          <div className="flex justify-end">
            <button type="submit" disabled={saving}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        )}
      </form>

      <OwnersSection assetId={id} assetOrgSlug={selectedOrg?.slug} />

      {isHost && (
        <>
          <ExposuresPanel exposures={asset.exposures} />
          <NatExposureEditor assetId={id} onExposuresChanged={loadAsset} />
        </>
      )}

      <p className="text-xs text-muted-foreground">
        Created {new Date(asset.created_at).toLocaleString()}
      </p>
    </div>
  );
}
