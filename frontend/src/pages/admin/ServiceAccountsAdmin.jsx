import { useEffect, useState } from 'react';
import { KeyRound, RefreshCw, Trash2, Copy, Check } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import api from '@/lib/axios';

// Parse a free-text allowlist (newline- or comma-separated CIDR/IP entries) into a
// clean array. The backend validates and normalises each entry (#696).
function parseAllowedIps(text) {
  return text
    .split(/[\n,]/)
    .map(s => s.trim())
    .filter(Boolean);
}

// Service accounts (PRD #694): non-human API principals a staff admin creates to
// connect external services. Org access is granted here via checkboxes (backed by
// OrganizationMembership); the account authenticates with a single API token shown
// exactly once, at creation and on rotation.

function OrgCheckboxes({ orgs, selected, onToggle, idPrefix }) {
  if (orgs.length === 0) {
    return <p className="text-xs text-muted-foreground">No organisations available.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {orgs.map(o => {
        const id = `${idPrefix}-${o.slug}`;
        const isOn = selected.includes(o.slug);
        return (
          <label
            key={o.slug}
            htmlFor={id}
            className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${
              isOn ? 'border-primary bg-primary/10 text-foreground' : 'border-border text-muted-foreground'
            }`}
          >
            <input
              id={id}
              type="checkbox"
              checked={isOn}
              onChange={() => onToggle(o.slug)}
              className="h-3.5 w-3.5"
            />
            {o.name}
          </label>
        );
      })}
    </div>
  );
}

function TokenReveal({ token, onDismiss }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <div className="rounded-md border border-primary bg-primary/5 p-4 space-y-2" role="alert">
      <p className="text-sm font-medium text-foreground">
        API token — copy it now. It will not be shown again.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all rounded bg-muted px-2 py-1 font-mono text-xs text-foreground">
          {token}
        </code>
        <Button size="sm" variant="outline" onClick={copy} className="shrink-0 text-xs">
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          <span className="ml-1">{copied ? 'Copied' : 'Copy'}</span>
        </Button>
      </div>
      <Button size="sm" variant="ghost" onClick={onDismiss} className="text-xs">
        Dismiss
      </Button>
    </div>
  );
}

function ServiceAccountRow({ account, orgs, onChanged, onRevealToken }) {
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState(account.orgs.map(o => o.slug));
  const [allowedIpsText, setAllowedIpsText] = useState((account.allowed_ips || []).join('\n'));
  const [saveError, setSaveError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function toggle(slug) {
    setSelected(s => (s.includes(slug) ? s.filter(x => x !== slug) : [...s, slug]));
  }

  function resetFields() {
    setSelected(account.orgs.map(o => o.slug));
    setAllowedIpsText((account.allowed_ips || []).join('\n'));
    setSaveError(null);
  }

  function startEditing() {
    resetFields();
    setEditing(true);
  }

  function cancelEditing() {
    resetFields();
    setEditing(false);
  }

  async function save() {
    setBusy(true);
    setSaveError(null);
    try {
      await api.patch(`/api/security/service-accounts/${account.id}/`, {
        org_slugs: selected,
        allowed_ips: parseAllowedIps(allowedIpsText),
      });
      setEditing(false);
      onChanged();
    } catch (err) {
      setSaveError(err.response?.data?.detail || 'Failed to save changes.');
    } finally {
      setBusy(false);
    }
  }

  async function rotate() {
    setBusy(true);
    try {
      const res = await api.post(`/api/security/service-accounts/${account.id}/rotate-token/`);
      onRevealToken(res.data.token);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.delete(`/api/security/service-accounts/${account.id}/`);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-border p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-foreground break-words">{account.name}</p>
          {account.description && (
            <p className="text-sm text-muted-foreground break-words">{account.description}</p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {account.created_by_username ? `Created by ${account.created_by_username}` : 'Created'}
            {account.created_at ? ` · ${new Date(account.created_at).toLocaleDateString()}` : ''}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {account.last_used_at ? (
              <>
                Last used {new Date(account.last_used_at).toLocaleString()}
                {account.last_used_ip ? ` from ${account.last_used_ip}` : ''}
              </>
            ) : (
              'Never used'
            )}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={rotate} className="text-xs">
            <RefreshCw className="h-3 w-3 mr-1" /> Rotate token
          </Button>
          {confirmDelete ? (
            <>
              <Button size="sm" variant="destructive" disabled={busy} onClick={remove} className="text-xs">
                Confirm
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(false)} className="text-xs">
                Cancel
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setConfirmDelete(true)} className="text-xs">
              <Trash2 className="h-3 w-3 mr-1" /> Revoke
            </Button>
          )}
        </div>
      </div>

      <div>
        {editing ? (
          <div className="space-y-3">
            <div className="space-y-1">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Orgs</span>
              <OrgCheckboxes orgs={orgs} selected={selected} onToggle={toggle} idPrefix={`edit-${account.id}`} />
            </div>
            <div className="space-y-1">
              <Label htmlFor={`allowed-ips-${account.id}`} className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                IP allowlist
              </Label>
              <Textarea
                id={`allowed-ips-${account.id}`}
                value={allowedIpsText}
                onChange={e => setAllowedIpsText(e.target.value)}
                placeholder="One IP or CIDR range per line, e.g. 203.0.113.0/24"
                className="font-mono text-xs"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                One IP or CIDR range per line. Leave empty to allow any source IP.
              </p>
            </div>
            {saveError && <p className="text-xs text-destructive">{saveError}</p>}
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} onClick={save} className="text-xs">Save</Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={cancelEditing}
                className="text-xs"
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Orgs:</span>
              {account.orgs.length === 0 ? (
                <span className="text-sm text-muted-foreground">None</span>
              ) : (
                account.orgs.map(o => (
                  <span key={o.slug} className="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">{o.name}</span>
                ))
              )}
              <button onClick={startEditing} className="text-xs font-medium text-primary hover:underline">
                Edit
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">IP allowlist:</span>
              {(account.allowed_ips || []).length === 0 ? (
                <span className="text-sm text-muted-foreground">Any IP</span>
              ) : (
                account.allowed_ips.map(ip => (
                  <span key={ip} className="rounded-full bg-muted px-2 py-0.5 font-mono text-xs text-foreground">{ip}</span>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ServiceAccountsAdmin() {
  const [accounts, setAccounts] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedOrgs, setSelectedOrgs] = useState([]);
  const [allowedIpsText, setAllowedIpsText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [revealedToken, setRevealedToken] = useState(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const [accRes, orgRes] = await Promise.all([
        api.get('/api/security/service-accounts/'),
        api.get('/api/security/organizations/'),
      ]);
      setAccounts(accRes.data);
      setOrgs(orgRes.data);
    } catch {
      setError('Failed to load service accounts.');
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function toggleCreateOrg(slug) {
    setSelectedOrgs(s => (s.includes(slug) ? s.filter(x => x !== slug) : [...s, slug]));
  }

  async function create(e) {
    e.preventDefault();
    if (!name.trim()) { setFormError('Name is required.'); return; }
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post('/api/security/service-accounts/', {
        name: name.trim(),
        description: description.trim(),
        org_slugs: selectedOrgs,
        allowed_ips: parseAllowedIps(allowedIpsText),
      });
      setRevealedToken(res.data.token);
      setName('');
      setDescription('');
      setSelectedOrgs([]);
      setAllowedIpsText('');
      load();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to create service account.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4">
      <div className="flex items-center gap-2">
        <KeyRound className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-xl font-semibold text-foreground">Service Accounts</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Non-human API accounts for connecting external services. Each account is scoped to the
        organisations you grant it and authenticates with an API token — it has no interactive
        login and no staff powers.
      </p>

      {revealedToken && (
        <TokenReveal token={revealedToken} onDismiss={() => setRevealedToken(null)} />
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New service account</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={create} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="sa-name">Name</Label>
              <Input id="sa-name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. CI pipeline" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sa-desc">Description (optional)</Label>
              <Input id="sa-desc" value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this used for?" />
            </div>
            <div className="space-y-1">
              <Label>Organisations</Label>
              <OrgCheckboxes orgs={orgs} selected={selectedOrgs} onToggle={toggleCreateOrg} idPrefix="new" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sa-allowed-ips">IP allowlist (optional)</Label>
              <Textarea
                id="sa-allowed-ips"
                value={allowedIpsText}
                onChange={e => setAllowedIpsText(e.target.value)}
                placeholder="One IP or CIDR range per line, e.g. 203.0.113.0/24"
                className="font-mono text-xs"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                Restrict which source IPs may use this token. Leave empty to allow any IP.
              </p>
            </div>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create service account'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : accounts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No service accounts yet.</p>
        ) : (
          accounts.map(account => (
            <ServiceAccountRow
              key={account.id}
              account={account}
              orgs={orgs}
              onChanged={load}
              onRevealToken={setRevealedToken}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default ServiceAccountsAdmin;
