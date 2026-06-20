import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
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

function CreateAssetModal({ open, onClose, orgSlug, onCreated }) {
  const [form, setForm] = useState({ name: '', agent_name: '', ip_address: '', role: '', is_permanent: false });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ name: '', agent_name: '', ip_address: '', role: '', is_permanent: false });
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
        role: form.role || null,
        is_permanent: form.is_permanent,
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
          <div>
            <label className="block text-sm font-medium text-foreground mb-1" htmlFor="new-role">Role</label>
            <select
              id="new-role"
              value={form.role}
              onChange={e => set('role', e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {ASSET_ROLES.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
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

function BulkUpdateModal({ open, onClose, selectedIds, orgSlug, onUpdated }) {
  const [isPermanent, setIsPermanent] = useState(null); // null = no change
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setIsPermanent(null);
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  async function submit(e) {
    e.preventDefault();
    if (isPermanent === null) {
      setError('Select at least one setting to update.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await api.post('/api/assets/bulk/', {
        ids: selectedIds,
        is_permanent: isPermanent,
      });
      onUpdated(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update assets.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">
          Bulk update {selectedIds.length} asset{selectedIds.length !== 1 ? 's' : ''}
        </h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <p className="text-sm font-medium text-foreground mb-2">Permanent status</p>
            <div className="flex gap-2">
              {[
                { label: 'No change', value: null },
                { label: 'Set permanent', value: true },
                { label: 'Unset permanent', value: false },
              ].map(opt => (
                <button
                  key={String(opt.value)}
                  type="button"
                  onClick={() => setIsPermanent(opt.value)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium border transition-colors ${
                    isPermanent === opt.value
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background text-foreground border-border hover:bg-accent'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={saving}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {saving ? 'Updating…' : 'Apply'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AssetRow({ asset, selected, onToggle, onDeleted }) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!confirm(`Delete asset "${asset.name}"?`)) return;
    setDeleting(true);
    try {
      await api.delete(`/api/assets/${asset.id}/`);
      onDeleted(asset.id);
    } catch {
      alert('Failed to delete asset.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
      <td className="px-4 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(asset.id)}
          className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
          aria-label={`Select ${asset.name}`}
        />
      </td>
      <td className="px-4 py-3 font-medium text-foreground">
        <Link to={`/assets/${asset.id}`} className="hover:underline">{asset.name}</Link>
      </td>
      <td className="px-4 py-3 text-muted-foreground capitalize">{asset.kind}</td>
      <td className="px-4 py-3 text-muted-foreground">{asset.agent_name || '—'}</td>
      <td className="px-4 py-3 text-muted-foreground">{asset.ip_address || '—'}</td>
      <td className="px-4 py-3">
        {asset.role ? (
          <span className="inline-flex items-center rounded-full bg-sky-100 dark:bg-sky-900/30 px-2 py-0.5 text-xs text-sky-700 dark:text-sky-400">
            {ASSET_ROLES.find(r => r.value === asset.role)?.label ?? asset.role}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
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
      </td>
      <td className="px-4 py-3 text-muted-foreground text-xs">
        {asset.last_seen_at ? new Date(asset.last_seen_at).toLocaleString() : '—'}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <Link to={`/assets/${asset.id}`} className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors">
            Edit
          </Link>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function AssetsPage() {
  const { selectedOrg } = useOrganization();
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [internetFacingOnly, setInternetFacingOnly] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

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
    const params = selectedOrg ? { org: selectedOrg.slug } : {};
    api.get('/api/assets/', { params })
      .then(res => setAssets(res.data.results || res.data))
      .catch(() => setError('Failed to load assets.'))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  const filtered = assets
    .filter(a => !internetFacingOnly || a.internet_facing)
    .filter(a =>
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      (a.agent_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (a.ip_address || '').toLowerCase().includes(search.toLowerCase())
    );

  const sorted = [...filtered].sort((a, b) => {
    const dir = sortOrder === 'asc' ? 1 : -1;
    if (sortKey === 'last_seen_at') {
      const av = a.last_seen_at ? new Date(a.last_seen_at).getTime() : null;
      const bv = b.last_seen_at ? new Date(b.last_seen_at).getTime() : null;
      if (av === bv) return 0;
      if (av === null) return 1; // nulls last regardless of direction
      if (bv === null) return -1;
      return (av - bv) * dir;
    }
    const av = (a[sortKey] || '').toString().toLowerCase();
    const bv = (b[sortKey] || '').toString().toLowerCase();
    return av.localeCompare(bv) * dir;
  });

  const allFilteredSelected = sorted.length > 0 && sorted.every(a => selected.has(a.id));

  function toggleAll() {
    if (allFilteredSelected) {
      setSelected(prev => {
        const next = new Set(prev);
        filtered.forEach(a => next.delete(a.id));
        return next;
      });
    } else {
      setSelected(prev => {
        const next = new Set(prev);
        filtered.forEach(a => next.add(a.id));
        return next;
      });
    }
  }

  function toggleOne(id) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleBulkUpdated(updatedAssets) {
    const byId = Object.fromEntries(updatedAssets.map(a => [a.id, a]));
    setAssets(prev => prev.map(a => byId[a.id] ?? a));
    setSelected(new Set());
  }

  const selectedIds = [...selected];

  return (
    <div className="space-y-4 p-6">
      <CreateAssetModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        orgSlug={selectedOrg?.slug}
        onCreated={asset => setAssets(prev => [...prev, asset].sort((a, b) => a.name.localeCompare(b.name)))}
      />
      <BulkUpdateModal
        open={bulkOpen}
        onClose={() => setBulkOpen(false)}
        selectedIds={selectedIds}
        orgSlug={selectedOrg?.slug}
        onUpdated={handleBulkUpdated}
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

      <div className="flex items-center gap-3">
        <input
          type="search"
          placeholder="Search assets…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-64"
        />
        <button
          type="button"
          onClick={() => setInternetFacingOnly(v => !v)}
          className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
            internetFacingOnly
              ? 'border-orange-400 bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
              : 'border-border bg-background text-foreground hover:bg-accent'
          }`}
        >
          Internet-facing
        </button>
        {selected.size > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-1.5">
            <span className="text-sm text-foreground font-medium">{selected.size} selected</span>
            <button
              onClick={() => setBulkOpen(true)}
              className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Bulk update
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
            {search || internetFacingOnly ? 'No assets match your filters.' : 'No assets yet.'}
          </p>
        ) : sorted.map(asset => (
          <div key={asset.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(asset.id)}
                onChange={() => toggleOne(asset.id)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                aria-label={`Select ${asset.name}`}
              />
              <Link to={`/assets/${asset.id}`} className="font-medium text-foreground hover:underline">{asset.name}</Link>
              <span className="ml-auto text-xs text-muted-foreground capitalize">{asset.kind}</span>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              {asset.agent_name && (<><dt className="text-muted-foreground">Agent</dt><dd className="text-foreground">{asset.agent_name}</dd></>)}
              {asset.ip_address && (<><dt className="text-muted-foreground">IP</dt><dd className="text-foreground">{asset.ip_address}</dd></>)}
              {asset.role && (<><dt className="text-muted-foreground">Role</dt><dd className="text-foreground">{ASSET_ROLES.find(r => r.value === asset.role)?.label ?? asset.role}</dd></>)}
              <dt className="text-muted-foreground">Last seen</dt>
              <dd className="text-foreground">{asset.last_seen_at ? new Date(asset.last_seen_at).toLocaleString() : '—'}</dd>
            </dl>
            <div className="flex flex-wrap items-center gap-1">
              {asset.is_active === false
                ? <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-xs text-muted-foreground">inactive</span>
                : <span className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-xs text-green-700 dark:text-green-400">active</span>}
              {asset.is_permanent && <span className="inline-flex items-center rounded-full bg-violet-100 dark:bg-violet-900/30 px-2 py-0.5 text-xs text-violet-700 dark:text-violet-400">permanent</span>}
              {asset.internet_facing && <span className="inline-flex items-center rounded-full bg-orange-100 dark:bg-orange-900/30 px-2 py-0.5 text-xs text-orange-700 dark:text-orange-400">internet-facing</span>}
              <Link to={`/assets/${asset.id}`} className="ml-auto rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors">Edit</Link>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={allFilteredSelected}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                  aria-label="Select all"
                />
              </th>
              {[
                { key: 'name', label: 'Name' },
                { key: 'kind', label: 'Kind' },
              ].map(({ key, label }) => (
                <th key={key} className="px-4 py-3 text-left font-medium text-muted-foreground">
                  <button onClick={() => setSort(key)} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label={`Sort by ${label}`}>
                    {label}
                    {sortKey === key && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                  </button>
                </th>
              ))}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Agent Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP Address</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status / Exposure</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                <button onClick={() => setSort('last_seen_at')} className="flex items-center gap-1 hover:text-foreground transition-colors" aria-label="Sort by Last Seen">
                  Last Seen
                  {sortKey === 'last_seen_at' && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
                </button>
              </th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : sorted.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                  {search || internetFacingOnly ? 'No assets match your filters.' : 'No assets yet.'}
                </td>
              </tr>
            ) : sorted.map(asset => (
              <AssetRow
                key={asset.id}
                asset={asset}
                selected={selected.has(asset.id)}
                onToggle={toggleOne}
                onDeleted={id => {
                  setAssets(prev => prev.filter(a => a.id !== id));
                  setSelected(prev => { const next = new Set(prev); next.delete(id); return next; });
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
