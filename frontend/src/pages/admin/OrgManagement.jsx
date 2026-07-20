import { useEffect, useMemo, useState } from 'react';
import {
  Shield, ChevronRight, UserPlus, X, Search, Users, SlidersHorizontal,
  Network, ListFilter, Plus,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import api from '@/lib/axios';

const ROLE_LABELS = { member: 'Member', staff: 'Staff', admin: 'Admin' };
const STATUS_CLASSES = {
  pending:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  expired:  'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};
const PROMPT_MAX = 4000;

function SavedFlash({ saved, error }) {
  if (error) return <p className="text-xs text-destructive">{error}</p>;
  if (saved) return <p className="text-xs text-green-600 dark:text-green-400">Saved.</p>;
  return null;
}

function InfraBadge({ org }) {
  if (!org.is_infrastructure) return null;
  return <Badge variant="secondary" className="text-[10px]">Infrastructure</Badge>;
}

/* ---------------------------------------------------------- Users section */

function InviteDialog({ org, onClose, onCreated }) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState('member');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post(`/api/security/organizations/${org.slug}/invite/`, {
        email: email.trim(),
        full_name: fullName.trim(),
        role,
      });
      onCreated(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to send invitation.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">Invite user to {org.name}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground" htmlFor="invite-email">Email</label>
            <Input
              id="invite-email"
              type="email"
              placeholder="user@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground" htmlFor="invite-name">Full name</label>
            <Input
              id="invite-name"
              placeholder="Jane Smith"
              value={fullName}
              onChange={e => setFullName(e.target.value)}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-foreground" htmlFor="invite-role">Role</label>
            <select
              id="invite-role"
              value={role}
              onChange={e => setRole(e.target.value)}
              disabled={submitting}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="member">Member</option>
              <option value="staff">Staff</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-3 pt-1">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !email.trim() || !fullName.trim()}>
              {submitting ? 'Sending…' : 'Send invitation'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UsersSection({ org }) {
  const [invitations, setInvitations] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);

  useEffect(() => {
    if (org.is_infrastructure) return;
    let live = true;
    setLoading(true);
    api.get(`/api/security/organizations/${org.slug}/invite/`)
      .then(res => { if (live) setInvitations(res.data); })
      .catch(() => { if (live) setInvitations([]); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [org.slug, org.is_infrastructure]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Members &amp; invitations</h3>
        {/* The Infrastructure pseudo-org (ADR-0017) has no members — invite does
            not apply to it. Its per-org settings stay editable under the other tabs. */}
        {!org.is_infrastructure && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowDialog(true)}
            aria-label={`Invite user to ${org.name}`}
          >
            <UserPlus className="h-3.5 w-3.5 mr-1" /> Invite
          </Button>
        )}
      </div>

      {org.is_infrastructure && (
        <p className="text-sm text-muted-foreground">The Infrastructure organisation has no members.</p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading invitations…</p>}
      {!loading && invitations !== null && invitations.length === 0 && !org.is_infrastructure && (
        <p className="text-sm text-muted-foreground">No invitations yet.</p>
      )}

      {!loading && invitations && invitations.length > 0 && (
        <>
          {/* Mobile card list */}
          <div className="space-y-2 sm:hidden">
            {invitations.map(inv => (
              <div key={inv.id} className="rounded-md border border-border p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="break-all font-medium text-foreground">{inv.email}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[inv.status] ?? ''}`}>
                    {inv.status}
                  </span>
                </div>
                <p className="text-muted-foreground">
                  {inv.full_name} · {ROLE_LABELS[inv.role] ?? inv.role}
                </p>
              </div>
            ))}
          </div>

          {/* Desktop table */}
          <table className="hidden w-full text-sm sm:table" aria-label={`Invitations for ${org.name}`}>
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-1.5 font-medium">Email</th>
                <th className="pb-1.5 font-medium">Name</th>
                <th className="pb-1.5 font-medium">Role</th>
                <th className="pb-1.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map(inv => (
                <tr key={inv.id} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 break-all text-foreground">{inv.email}</td>
                  <td className="py-1.5 text-muted-foreground">{inv.full_name}</td>
                  <td className="py-1.5 text-muted-foreground">{ROLE_LABELS[inv.role] ?? inv.role}</td>
                  <td className="py-1.5">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[inv.status] ?? ''}`}>
                      {inv.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {showDialog && (
        <InviteDialog
          org={org}
          onClose={() => setShowDialog(false)}
          onCreated={inv => setInvitations(prev => [inv, ...(prev ?? [])])}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------- AI Triage section */

function TriageSection({ org }) {
  const [context, setContext] = useState(org.triage_prompt_context ?? '');
  const [fp, setFp] = useState(org.triage_fp_threshold ?? 0.95);
  const [work, setWork] = useState(org.triage_work_threshold ?? 0.95);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function save(e) {
    e.preventDefault();
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.patch(`/api/security/organizations/${org.slug}/`, {
        triage_prompt_context: context || null,
        triage_fp_threshold: Number(fp),
        triage_work_threshold: Number(work),
      });
      setSaved(true);
    } catch (err) {
      setError(err.response?.data?.triage_prompt_context?.[0] ?? 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-foreground" htmlFor={`triage-context-${org.slug}`}>
          Custom triage instructions
        </label>
        <span className={`text-xs ${context.length > PROMPT_MAX ? 'text-destructive' : 'text-muted-foreground'}`}>
          {context.length} / {PROMPT_MAX}
        </span>
      </div>
      <Textarea
        id={`triage-context-${org.slug}`}
        rows={4}
        placeholder="e.g. We are a healthcare provider. Treat PHI-related alerts as critical. Ignore SSH from 10.0.0.5 (jump host)."
        value={context}
        onChange={e => { setContext(e.target.value); setSaved(false); }}
        disabled={saving}
        className="text-sm resize-y"
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`triage-fp-${org.slug}`}>
            False-positive auto-close threshold
          </label>
          <input
            id={`triage-fp-${org.slug}`}
            type="number" min="0" max="1" step="0.01"
            value={fp}
            onChange={e => { setFp(e.target.value); setSaved(false); }}
            disabled={saving}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`triage-work-${org.slug}`}>
            Agentic work-confidence threshold
          </label>
          <input
            id={`triage-work-${org.slug}`}
            type="number" min="0" max="1" step="0.01"
            value={work}
            onChange={e => { setWork(e.target.value); setSaved(false); }}
            disabled={saving}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
          <p className="text-[11px] text-muted-foreground">
            Minimum confidence before the Triage Agent works the incident unattended.
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between pt-1">
        <SavedFlash saved={saved} error={error} />
        <Button type="submit" size="sm" disabled={saving || context.length > PROMPT_MAX}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </form>
  );
}

/* -------------------------------------------------- Network & Alerts section */

function IocSettings({ org }) {
  const [ranges, setRanges] = useState((org.internal_ip_ranges ?? []).join('\n'));
  const [domains, setDomains] = useState((org.owned_domains ?? []).join('\n'));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function save(e) {
    e.preventDefault();
    setSaving(true); setError(null); setSaved(false);
    const toList = t => t.split(/[\n,]/).map(s => s.trim()).filter(Boolean);
    try {
      await api.patch(`/api/security/organizations/${org.slug}/`, {
        internal_ip_ranges: toList(ranges),
        owned_domains: toList(domains),
      });
      setSaved(true);
    } catch (err) {
      setError(
        err.response?.data?.internal_ip_ranges?.[0]
        ?? err.response?.data?.owned_domains?.[0]
        ?? 'Failed to save IOC exclusions.'
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">IOC exclusions</h3>
        <p className="text-xs text-muted-foreground">
          Indicators inside these internal IP ranges or owned domains are excluded from
          automatic IOC extraction. One entry per line (or comma-separated).
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`ioc-ranges-${org.slug}`}>
            Internal IP ranges (CIDR)
          </label>
          <Textarea
            id={`ioc-ranges-${org.slug}`}
            rows={4}
            placeholder={'10.0.0.0/8\n192.168.0.0/16\nfd00::/8'}
            value={ranges}
            onChange={e => { setRanges(e.target.value); setSaved(false); }}
            disabled={saving}
            className="text-xs font-mono resize-y"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground" htmlFor={`ioc-domains-${org.slug}`}>
            Owned domains
          </label>
          <Textarea
            id={`ioc-domains-${org.slug}`}
            rows={4}
            placeholder={'corp.example\nexample.com'}
            value={domains}
            onChange={e => { setDomains(e.target.value); setSaved(false); }}
            disabled={saving}
            className="text-xs font-mono resize-y"
          />
        </div>
      </div>
      <div className="flex items-center justify-between">
        <SavedFlash saved={saved} error={error} />
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? 'Saving…' : 'Save IOC exclusions'}
        </Button>
      </div>
    </form>
  );
}

function AlertSettings({ org }) {
  const [lookback, setLookback] = useState(org.alert_match_lookback_days ?? 30);
  const [threshold, setThreshold] = useState(org.alert_auto_promote_threshold ?? 5);
  const [win, setWin] = useState(org.alert_auto_promote_window_minutes ?? 60);
  const [tz, setTz] = useState(org.timezone ?? 'UTC');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function save(e) {
    e.preventDefault();
    setSaving(true); setError(null); setSaved(false);
    try {
      await api.patch(`/api/security/organizations/${org.slug}/`, {
        alert_match_lookback_days: Number(lookback),
        alert_auto_promote_threshold: Number(threshold),
        alert_auto_promote_window_minutes: Number(win),
        timezone: tz.trim() || 'UTC',
      });
      setSaved(true);
    } catch (err) {
      setError(err.response?.data?.timezone?.[0] ?? 'Failed to save alert settings.');
    } finally {
      setSaving(false);
    }
  }

  const inputCls = 'rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground';
  const field = (id, label, node) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground" htmlFor={id}>{label}</label>
      {node}
    </div>
  );

  return (
    <form onSubmit={save} className="space-y-3">
      <h3 className="text-sm font-semibold text-foreground">Alert settings</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {field(`alert-lookback-${org.slug}`, 'Match lookback (days)',
          <input id={`alert-lookback-${org.slug}`} type="number" min={1} value={lookback}
            onChange={e => { setLookback(e.target.value); setSaved(false); }} disabled={saving} className={inputCls} />)}
        {field(`alert-threshold-${org.slug}`, 'Auto-promote threshold',
          <input id={`alert-threshold-${org.slug}`} type="number" min={1} value={threshold}
            onChange={e => { setThreshold(e.target.value); setSaved(false); }} disabled={saving} className={inputCls} />)}
        {field(`alert-window-${org.slug}`, 'Promote window (min)',
          <input id={`alert-window-${org.slug}`} type="number" min={1} value={win}
            onChange={e => { setWin(e.target.value); setSaved(false); }} disabled={saving} className={inputCls} />)}
        {field(`org-timezone-${org.slug}`, 'Timezone (IANA)',
          <input id={`org-timezone-${org.slug}`} type="text" value={tz} placeholder="e.g. Europe/Amsterdam"
            onChange={e => { setTz(e.target.value); setSaved(false); }} disabled={saving} className={inputCls} />)}
      </div>
      <p className="text-xs text-muted-foreground">
        Used to evaluate Scheduled Search Rule time-of-day windows in this org's local time.
      </p>
      <div className="flex items-center justify-between">
        <SavedFlash saved={saved} error={error} />
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? 'Saving…' : 'Save alert settings'}
        </Button>
      </div>
    </form>
  );
}

function NetworkSection({ org }) {
  return (
    <div className="space-y-6">
      <IocSettings org={org} />
      <div className="border-t border-border pt-4">
        <AlertSettings org={org} />
      </div>
    </div>
  );
}

/* ---------------------------------------------------- Detection Rules section */

function RuleMuteTable({ org, title, listUrl, muteUrl, emptyLabel }) {
  const [rules, setRules] = useState(null);
  const [loading, setLoading] = useState(false);
  const [togglingId, setTogglingId] = useState(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.get(`${listUrl}?org=${org.slug}`)
      .then(res => { if (live) setRules(res.data); })
      .catch(() => { if (live) setRules([]); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [org.slug, listUrl]);

  async function toggle(rule) {
    setTogglingId(rule.id);
    try {
      if (rule.muted) {
        await api.delete(`${muteUrl}${rule.id}/mute/?org=${org.slug}`);
      } else {
        await api.post(`${muteUrl}${rule.id}/mute/`, { org: org.slug });
      }
      setRules(prev => prev.map(r => (r.id === rule.id ? { ...r, muted: !r.muted } : r)));
    } catch {
      // leave state unchanged on error
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!loading && rules !== null && rules.length === 0 && (
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      )}
      {!loading && rules && rules.length > 0 && (
        <table className="w-full text-sm" aria-label={`${title} for ${org.name}`}>
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-1.5 font-medium">Rule</th>
              <th className="pb-1.5 font-medium">Severity</th>
              <th className="pb-1.5 font-medium text-right">Mute for this org</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(rule => (
              <tr key={rule.id} className="border-b border-border/50 last:border-0">
                <td className="py-1.5 text-foreground">{rule.name}</td>
                <td className="py-1.5 text-muted-foreground capitalize">{rule.severity}</td>
                <td className="py-1.5 text-right">
                  <Button
                    size="sm"
                    variant={rule.muted ? 'default' : 'outline'}
                    disabled={togglingId === rule.id}
                    onClick={() => toggle(rule)}
                    aria-label={rule.muted ? `Unmute ${rule.name} for ${org.name}` : `Mute ${rule.name} for ${org.name}`}
                  >
                    {togglingId === rule.id ? '…' : rule.muted ? 'Unmute' : 'Mute'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RulesSection({ org }) {
  return (
    <div className="space-y-6">
      <RuleMuteTable
        org={org}
        title="System Rules"
        emptyLabel="No system rules defined."
        listUrl="/api/correlations/org-system-rules/"
        muteUrl="/api/correlations/org-system-rules/"
      />
      <RuleMuteTable
        org={org}
        title="System Search Rules"
        emptyLabel="No system search rules defined."
        listUrl="/api/correlations/org-system-search-rules/"
        muteUrl="/api/correlations/org-system-search-rules/"
      />
    </div>
  );
}

/* -------------------------------------------------------------- tab catalogue */

const SECTIONS = [
  { key: 'users',   label: 'Users',            icon: Users,            render: org => <UsersSection org={org} /> },
  { key: 'triage',  label: 'AI Triage',        icon: SlidersHorizontal, render: org => <TriageSection org={org} /> },
  { key: 'rules',   label: 'Detection Rules',  icon: ListFilter,       render: org => <RulesSection org={org} /> },
  { key: 'network', label: 'Network & Alerts', icon: Network,          render: org => <NetworkSection org={org} /> },
];

/* --------------------------------------------------------------- rail + create */

function CreateOrgInline({ onCreated }) {
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function submit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    api.post('/api/security/organizations/', { name: name.trim() })
      .then(res => { onCreated(res.data); setName(''); })
      .catch(err => setError(err.response?.data?.detail ?? 'Failed to create organisation.'))
      .finally(() => setSubmitting(false));
  }

  return (
    <form onSubmit={submit} className="space-y-1">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Organisation name"
          value={name}
          onChange={e => setName(e.target.value)}
          disabled={submitting}
        />
        <Button type="submit" size="sm" disabled={submitting || !name.trim()}>
          {submitting ? '…' : <><Plus className="h-4 w-4 mr-1" />Create</>}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </form>
  );
}

/* --------------------------------------------------------------------- page */

function OrgManagement() {
  const [orgs, setOrgs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [section, setSection] = useState('users');
  const [query, setQuery] = useState('');

  useEffect(() => {
    api
      // Opt into the Infrastructure pseudo-org (ADR-0017) so its settings —
      // notably the AI-triage thresholds — are editable from this page. Other
      // callers keep the default tenants-only listing.
      .get('/api/security/organizations/?include_infrastructure=1')
      .then((res) => {
        setOrgs(res.data);
        setSelectedId(prev => prev ?? res.data[0]?.id ?? null);
      })
      .catch(() => setError('Failed to load organisations.'))
      .finally(() => setIsLoading(false));
  }, []);

  function handleCreated(org) {
    setOrgs(prev => [...prev, org].sort((a, b) => a.name.localeCompare(b.name)));
    setSelectedId(org.id);
    setSection('users');
  }

  const filtered = useMemo(
    () => orgs.filter(o => o.name.toLowerCase().includes(query.toLowerCase())),
    [orgs, query]
  );
  const selected = orgs.find(o => o.id === selectedId) ?? null;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Organisations</h1>
        <p className="text-sm text-muted-foreground">
          Manage customer organisations, their members, and per-org settings.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!isLoading && !error && orgs.length === 0 && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            <p className="text-sm text-muted-foreground">No organisations yet.</p>
            <CreateOrgInline onCreated={handleCreated} />
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && orgs.length > 0 && (
        <div className="flex flex-col gap-4 lg:h-[calc(100vh-12rem)] lg:flex-row">
          {/* Rail */}
          <div className="flex w-full flex-col rounded-lg border border-border bg-card lg:w-80 lg:shrink-0">
            <div className="space-y-2 border-b border-border p-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search organisations"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  className="pl-8"
                  aria-label="Search organisations"
                />
              </div>
              <CreateOrgInline onCreated={handleCreated} />
            </div>
            <div className="max-h-72 flex-1 overflow-y-auto p-2 lg:max-h-none">
              {filtered.map(org => (
                <button
                  key={org.id}
                  onClick={() => setSelectedId(org.id)}
                  aria-current={org.id === selectedId ? 'true' : undefined}
                  className={`mb-1 flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left transition-colors ${
                    org.id === selectedId ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-foreground">{org.name}</span>
                    <span className="block truncate font-mono text-xs text-muted-foreground">{org.slug}</span>
                  </span>
                  {org.is_infrastructure
                    ? <Shield className="h-3.5 w-3.5 shrink-0 text-blue-500" aria-label="Infrastructure" />
                    : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                </button>
              ))}
              {filtered.length === 0 && (
                <p className="p-3 text-sm text-muted-foreground">No matches.</p>
              )}
            </div>
          </div>

          {/* Detail */}
          <div className="flex min-w-0 flex-1 flex-col rounded-lg border border-border bg-card">
            {!selected ? (
              <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">
                Select an organisation.
              </div>
            ) : (
              <>
                <div className="border-b border-border p-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-foreground">{selected.name}</h2>
                    <InfraBadge org={selected} />
                  </div>
                  <p className="font-mono text-xs text-muted-foreground">
                    {selected.slug}{selected.wazuh_group ? ` · wazuh: ${selected.wazuh_group}` : ''}
                  </p>
                </div>
                <div className="flex gap-1 overflow-x-auto border-b border-border px-2">
                  {SECTIONS.map(s => {
                    const Icon = s.icon;
                    return (
                      <button
                        key={s.key}
                        onClick={() => setSection(s.key)}
                        aria-current={section === s.key ? 'page' : undefined}
                        className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                          section === s.key
                            ? 'border-foreground text-foreground'
                            : 'border-transparent text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        <Icon className="h-4 w-4" />{s.label}
                      </button>
                    );
                  })}
                </div>
                {/* Key on org id so switching orgs remounts the section with fresh
                    form state rather than carrying over the previous org's values. */}
                <div key={selected.id} className="flex-1 overflow-y-auto p-4">
                  {SECTIONS.find(s => s.key === section)?.render(selected)}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default OrgManagement;
