import { useState, useEffect, useMemo } from 'react';
import api from '@/lib/axios';

const PLATFORMS = ['linux', 'windows', 'macos'];

function PlatformBadge({ platform }) {
  const colors = {
    linux: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    windows: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    macos: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium ${colors[platform] ?? colors.linux}`}>
      {platform}
    </span>
  );
}

function ResponseEditor({ response, onUpdate, onCancel }) {
  const [name, setName] = useState(response.name);
  const [command, setCommand] = useState(response.command);
  const [platforms, setPlatforms] = useState(response.platforms || []);
  const [defaultArgs, setDefaultArgs] = useState(response.default_args || '');
  const [timeout, setTimeout_] = useState(String(response.timeout ?? 0));
  const [availableInOverview, setAvailableInOverview] = useState(response.available_in_security_overview);
  const [requiresConfirmation, setRequiresConfirmation] = useState(response.requires_confirmation);
  const [autonomousApproved, setAutonomousApproved] = useState(response.autonomous_triage_approved);
  const [saving, setSaving] = useState(false);

  function togglePlatform(p) {
    setPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  }

  async function handleSave() {
    if (!name.trim() || !command.trim()) return;
    setSaving(true);
    try {
      const res = await api.patch(`/api/wazuh-responses/${response.id}/`, {
        name: name.trim(),
        command: command.trim(),
        platforms,
        default_args: defaultArgs.trim(),
        timeout: Number(timeout) || 0,
        available_in_security_overview: availableInOverview,
        requires_confirmation: requiresConfirmation,
        autonomous_triage_approved: autonomousApproved,
      });
      onUpdate(res.data);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 max-w-2xl">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  disabled={saving}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Command</label>
                <input
                  value={command}
                  onChange={e => setCommand(e.target.value)}
                  disabled={saving}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Platforms</label>
              <div className="flex gap-3">
                {PLATFORMS.map(p => (
                  <label key={p} className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={platforms.includes(p)}
                      onChange={() => togglePlatform(p)}
                      disabled={saving}
                      className="rounded border-border"
                    />
                    {p}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Default args <span className="font-normal text-muted-foreground/70">(supports {'{{incident.id}}'}, {'{{asset.ip}}'}, etc.)</span>
              </label>
              <input
                value={defaultArgs}
                onChange={e => setDefaultArgs(e.target.value)}
                disabled={saving}
                placeholder="-name 'block-ip' -args {{asset.ip}}"
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm font-mono"
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Timeout (s, 0 = none)</label>
                <input
                  type="number"
                  value={timeout}
                  onChange={e => setTimeout_(e.target.value)}
                  disabled={saving}
                  min="0"
                  className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                />
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
                <input
                  type="checkbox"
                  checked={availableInOverview}
                  onChange={e => setAvailableInOverview(e.target.checked)}
                  disabled={saving}
                  className="rounded border-border"
                />
                Available in security overview
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
                <input
                  type="checkbox"
                  checked={requiresConfirmation}
                  onChange={e => setRequiresConfirmation(e.target.checked)}
                  disabled={saving}
                  className="rounded border-border"
                />
                Requires confirmation
              </label>
            </div>
            <label className="flex items-start gap-2 text-sm cursor-pointer rounded-md border border-red-300 bg-red-50 p-2 dark:border-red-900/50 dark:bg-red-950/30">
              <input
                type="checkbox"
                checked={autonomousApproved}
                onChange={e => setAutonomousApproved(e.target.checked)}
                disabled={saving}
                className="mt-0.5 rounded border-border"
              />
              <span>
                <span className="font-medium text-red-800 dark:text-red-300">Approve for autonomous triage</span>
                <span className="block text-xs text-red-700/80 dark:text-red-400/80">
                  Lets the unattended Triage Agent run this response with no human present, on high confidence.
                  This is <strong>global</strong> — it may auto-fire on <strong>any</strong> tenant's estate.
                  Distinct from “requires confirmation”. Approve only when this action is safe fleet-wide.
                </span>
              </span>
            </label>
            <div className="flex gap-2">
              <button onClick={handleSave} disabled={saving} className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50">
                Save
              </button>
              <button onClick={onCancel} className="text-xs text-muted-foreground hover:underline">
                Cancel
              </button>
            </div>
          </div>
  );
}

function FlagsCell({ response }) {
  return (
    <div className="flex flex-col gap-0.5">
      {response.available_in_security_overview && (
        <span className="text-xs text-green-700 dark:text-green-400">Overview</span>
      )}
      {response.requires_confirmation && (
        <span className="text-xs text-orange-700 dark:text-orange-400">Confirmation</span>
      )}
      {response.autonomous_triage_approved && (
        <span className="text-xs font-medium text-red-700 dark:text-red-400">Autonomous</span>
      )}
    </div>
  );
}

function CreateModal({ onClose, onCreate }) {
  const [name, setName] = useState('');
  const [command, setCommand] = useState('');
  const [platforms, setPlatforms] = useState([]);
  const [defaultArgs, setDefaultArgs] = useState('');
  const [timeout, setTimeout_] = useState('0');
  const [availableInOverview, setAvailableInOverview] = useState(false);
  const [requiresConfirmation, setRequiresConfirmation] = useState(false);
  const [autonomousApproved, setAutonomousApproved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  function togglePlatform(p) {
    setPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = {};
    if (!name.trim()) errs.name = 'Required.';
    if (!command.trim()) errs.command = 'Required.';
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setSaving(true);
    try {
      const res = await api.post('/api/wazuh-responses/', {
        name: name.trim(),
        command: command.trim(),
        platforms,
        default_args: defaultArgs.trim(),
        timeout: Number(timeout) || 0,
        available_in_security_overview: availableInOverview,
        requires_confirmation: requiresConfirmation,
        autonomous_triage_approved: autonomousApproved,
      });
      onCreate(res.data);
      onClose();
    } catch (err) {
      setErrors({ _: err.response?.data?.detail || 'Failed to create.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-background p-6 shadow-xl">
        <h2 className="mb-4 text-base font-semibold text-foreground">New Wazuh Active Response</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={saving}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.name && <p className="mt-0.5 text-xs text-red-600">{errors.name}</p>}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Command</label>
            <input
              value={command}
              onChange={e => setCommand(e.target.value)}
              disabled={saving}
              placeholder="firewall-drop"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.command && <p className="mt-0.5 text-xs text-red-600">{errors.command}</p>}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Platforms</label>
            <div className="flex gap-4">
              {PLATFORMS.map(p => (
                <label key={p} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={platforms.includes(p)}
                    onChange={() => togglePlatform(p)}
                    disabled={saving}
                    className="rounded border-border"
                  />
                  {p}
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Default args
            </label>
            <input
              value={defaultArgs}
              onChange={e => setDefaultArgs(e.target.value)}
              disabled={saving}
              placeholder="-name 'block-ip' -args {{asset.ip}}"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Timeout (s, 0 = none)</label>
              <input
                type="number"
                value={timeout}
                onChange={e => setTimeout_(e.target.value)}
                disabled={saving}
                min="0"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
              <input
                type="checkbox"
                checked={availableInOverview}
                onChange={e => setAvailableInOverview(e.target.checked)}
                disabled={saving}
                className="rounded border-border"
              />
              Available in overview
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer pt-5">
              <input
                type="checkbox"
                checked={requiresConfirmation}
                onChange={e => setRequiresConfirmation(e.target.checked)}
                disabled={saving}
                className="rounded border-border"
              />
              Requires confirmation
            </label>
          </div>
          <label className="flex items-start gap-2 text-sm cursor-pointer rounded-md border border-red-300 bg-red-50 p-2 dark:border-red-900/50 dark:bg-red-950/30">
            <input
              type="checkbox"
              checked={autonomousApproved}
              onChange={e => setAutonomousApproved(e.target.checked)}
              disabled={saving}
              className="mt-0.5 rounded border-border"
            />
            <span>
              <span className="font-medium text-red-800 dark:text-red-300">Approve for autonomous triage</span>
              <span className="block text-xs text-red-700/80 dark:text-red-400/80">
                Lets the unattended Triage Agent run this response with no human present, on high confidence.
                This is <strong>global</strong> — it may auto-fire on <strong>any</strong> tenant's estate.
                Distinct from “requires confirmation”. Approve only when this action is safe fleet-wide.
              </span>
            </span>
          </label>
          {errors._ && <p className="text-xs text-red-600">{errors._}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={saving} className="text-sm text-muted-foreground hover:underline">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {saving ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const SORT_COLUMNS = {
  name:    { label: 'Name',    defaultOrder: 'asc' },
  command: { label: 'Command', defaultOrder: 'asc' },
  status:  { label: 'Status',  defaultOrder: 'asc' },
};

export default function WazuhResponsesAdmin() {
  const [responses, setResponses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  const [search, setSearch] = useState('');
  const [platformFilter, setPlatformFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('active');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.get('/api/wazuh-responses/', { params: { include_archived: '1' } })
      .then(res => setResponses(res.data))
      .catch(() => setError('Failed to load Wazuh active responses.'))
      .finally(() => setLoading(false));
  }, []);

  async function setArchived(response, archived) {
    try {
      if (archived) {
        await api.delete(`/api/wazuh-responses/${response.id}/`);
        setResponses(prev => prev.map(r => r.id === response.id ? { ...r, archived: true } : r));
      } else {
        const res = await api.patch(`/api/wazuh-responses/${response.id}/`, { archived: false });
        setResponses(prev => prev.map(r => r.id === response.id ? res.data : r));
      }
    } catch {
      setError('Failed to update Wazuh active response.');
    }
  }

  function handleArchive(response) {
    return setArchived(response, true);
  }

  function handleUpdate(updated) {
    setResponses(prev => prev.map(r => r.id === updated.id ? updated : r));
    setEditingId(null);
  }

  function handleCreate(created) {
    setResponses(prev => [...prev, created]);
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
    let rows = responses.filter(r => {
      if (statusFilter === 'active' && r.archived) return false;
      if (statusFilter === 'archived' && !r.archived) return false;
      if (platformFilter !== 'all' && !(r.platforms || []).includes(platformFilter)) return false;
      if (!q) return true;
      return (
        (r.name || '').toLowerCase().includes(q) ||
        (r.command || '').toLowerCase().includes(q)
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      if (sortKey === 'status') return ((a.archived ? 1 : 0) - (b.archived ? 1 : 0)) * dir;
      return (a[sortKey] || '').toString().toLowerCase()
        .localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir;
    });
    return rows;
  }, [responses, search, platformFilter, statusFilter, sortKey, sortOrder]);

  const visibleIds = visible.map(r => r.id);
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
    const targets = visible.filter(r => selectedIds.has(r.id) && r.archived !== archived);
    for (const r of targets) {
      await setArchived(r, archived);
    }
    setSelectedIds(new Set());
    setBulkBusy(false);
  }

  function SortHeader({ field }) {
    return (
      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <button
          onClick={() => setSort(field)}
          className="flex items-center gap-1 uppercase hover:text-foreground transition-colors"
          aria-label={`Sort by ${SORT_COLUMNS[field].label}`}
        >
          {SORT_COLUMNS[field].label}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Wazuh Active Responses</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage the catalog of Wazuh active response commands.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
        >
          New response
        </button>
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <div className="mb-4 flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search responses…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search responses"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring w-52"
        />
        <select
          value={platformFilter}
          onChange={e => setPlatformFilter(e.target.value)}
          aria-label="Platform filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All platforms</option>
          {PLATFORMS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="active">Active</option>
          <option value="archived">Archived</option>
          <option value="all">All statuses</option>
        </select>
      </div>

      {selectedIds.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-border bg-card px-4 py-2">
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
          <p className="py-8 text-center text-sm text-muted-foreground">No Wazuh active responses configured.</p>
        ) : visible.map(r => (
          <div key={r.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-2">
            {editingId === r.id ? (
              <ResponseEditor response={r} onUpdate={handleUpdate} onCancel={() => setEditingId(null)} />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(r.id)}
                      onChange={() => toggleSelect(r.id)}
                      aria-label={`Select ${r.name}`}
                      className="mt-1 h-4 w-4 rounded border-border"
                    />
                    <div>
                      <p className="font-medium text-foreground leading-snug">{r.name}</p>
                      <p className="font-mono text-xs text-muted-foreground">{r.command}</p>
                    </div>
                  </div>
                  {r.archived
                    ? <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">Archived</span>
                    : <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-xs text-green-800 dark:bg-green-900/30 dark:text-green-400">Active</span>}
                </div>
                <div className="flex flex-wrap gap-1">
                  {(r.platforms || []).map(p => <PlatformBadge key={p} platform={p} />)}
                </div>
                <FlagsCell response={r} />
                <div className="flex gap-2">
                  <button onClick={() => setEditingId(r.id)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
                  <button onClick={() => setArchived(r, !r.archived)} className="text-xs text-red-600 hover:underline">
                    {r.archived ? 'Unarchive' : 'Archive'}
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block rounded-lg border border-border bg-card">
        <table className="w-full text-left">
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
              <SortHeader field="command" />
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Platforms</th>
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Timeout</th>
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Flags</th>
              <SortHeader field="status" />
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No Wazuh active responses configured.
                </td>
              </tr>
            ) : (
              visible.map(r => (
                editingId === r.id ? (
                  <tr key={r.id} className="border-b border-border bg-accent/30">
                    <td className="px-4 py-3" />
                    <td className="px-4 py-3" colSpan={7}>
                      <ResponseEditor response={r} onUpdate={handleUpdate} onCancel={() => setEditingId(null)} />
                    </td>
                  </tr>
                ) : (
                  <tr key={r.id} className="border-b border-border last:border-0 hover:bg-accent/20">
                    <td className="px-4 py-3 w-8">
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.name}`}
                        checked={selectedIds.has(r.id)}
                        onChange={() => toggleSelect(r.id)}
                        className="rounded border-border"
                      />
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-foreground">{r.name}</td>
                    <td className="px-4 py-3 text-sm font-mono text-muted-foreground">{r.command}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(r.platforms || []).map(p => <PlatformBadge key={p} platform={p} />)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {r.timeout === 0 ? 'No timeout' : `${r.timeout}s`}
                    </td>
                    <td className="px-4 py-3 text-sm"><FlagsCell response={r} /></td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {r.archived
                        ? <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-700 dark:text-gray-400">Archived</span>
                        : <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-green-800 dark:bg-green-900/30 dark:text-green-400">Active</span>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => setEditingId(r.id)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
                        <button onClick={() => setArchived(r, !r.archived)} className="text-xs text-red-600 hover:underline">
                          {r.archived ? 'Unarchive' : 'Archive'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              ))
            )}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}
    </div>
  );
}
