import { useState, useEffect } from 'react';
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

function ResponseRow({ response, onArchive, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(response.name);
  const [command, setCommand] = useState(response.command);
  const [platforms, setPlatforms] = useState(response.platforms || []);
  const [defaultArgs, setDefaultArgs] = useState(response.default_args || '');
  const [timeout, setTimeout_] = useState(String(response.timeout ?? 0));
  const [availableInOverview, setAvailableInOverview] = useState(response.available_in_security_overview);
  const [requiresConfirmation, setRequiresConfirmation] = useState(response.requires_confirmation);
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
      });
      onUpdate(res.data);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <tr className="border-b border-border bg-accent/30">
        <td className="px-4 py-3" colSpan={7}>
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
            <div className="flex gap-2">
              <button onClick={handleSave} disabled={saving} className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50">
                Save
              </button>
              <button onClick={() => setEditing(false)} className="text-xs text-muted-foreground hover:underline">
                Cancel
              </button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/20">
      <td className="px-4 py-3 text-sm font-medium text-foreground">{response.name}</td>
      <td className="px-4 py-3 text-sm font-mono text-muted-foreground">{response.command}</td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {(response.platforms || []).map(p => <PlatformBadge key={p} platform={p} />)}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {response.timeout === 0 ? 'No timeout' : `${response.timeout}s`}
      </td>
      <td className="px-4 py-3 text-sm">
        <div className="flex flex-col gap-0.5">
          {response.available_in_security_overview && (
            <span className="text-xs text-green-700 dark:text-green-400">Overview</span>
          )}
          {response.requires_confirmation && (
            <span className="text-xs text-orange-700 dark:text-orange-400">Confirmation</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {response.archived && <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-700 dark:text-gray-400">Archived</span>}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <button onClick={() => setEditing(true)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
          {!response.archived && (
            <button onClick={() => onArchive(response)} className="text-xs text-red-600 hover:underline">Archive</button>
          )}
        </div>
      </td>
    </tr>
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

export default function WazuhResponsesAdmin() {
  const [responses, setResponses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get('/api/wazuh-responses/', { params: { include_archived: includeArchived ? '1' : '0' } })
      .then(res => setResponses(res.data))
      .catch(() => setError('Failed to load Wazuh active responses.'))
      .finally(() => setLoading(false));
  }, [includeArchived]);

  function handleArchive(response) {
    api.delete(`/api/wazuh-responses/${response.id}/`)
      .then(() => {
        if (includeArchived) {
          setResponses(prev => prev.map(r => r.id === response.id ? { ...r, archived: true } : r));
        } else {
          setResponses(prev => prev.filter(r => r.id !== response.id));
        }
      });
  }

  function handleUpdate(updated) {
    setResponses(prev => prev.map(r => r.id === updated.id ? updated : r));
  }

  function handleCreate(created) {
    setResponses(prev => [...prev, created]);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Wazuh Active Responses</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage the catalog of Wazuh active response commands.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={e => setIncludeArchived(e.target.checked)}
              className="rounded border-border"
            />
            Show archived
          </label>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          >
            New response
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="rounded-lg border border-border bg-card">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Name</th>
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Command</th>
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Platforms</th>
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Timeout</th>
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Flags</th>
                <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {responses.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    No Wazuh active responses configured.
                  </td>
                </tr>
              ) : (
                responses.map(r => (
                  <ResponseRow
                    key={r.id}
                    response={r}
                    onArchive={handleArchive}
                    onUpdate={handleUpdate}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}
    </div>
  );
}
