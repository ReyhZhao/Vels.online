import { useEffect, useState } from 'react';
import { Shield, ChevronDown, ChevronRight, UserPlus, X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/axios';

const ROLE_LABELS = { member: 'Member', staff: 'Staff', admin: 'Admin' };
const STATUS_CLASSES = {
  pending:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  expired:  'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

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

const PROMPT_MAX = 4000;

function OrgRow({ org }) {
  const [expanded, setExpanded] = useState(false);
  const [invitations, setInvitations] = useState(null);
  const [loadingInvites, setLoadingInvites] = useState(false);
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [triageContext, setTriageContext] = useState(org.triage_prompt_context ?? '');
  const [savingTriage, setSavingTriage] = useState(false);
  const [triageSaveError, setTriageSaveError] = useState(null);
  const [triageSaved, setTriageSaved] = useState(false);

  const [alertLookback, setAlertLookback] = useState(org.alert_match_lookback_days ?? 30);
  const [alertThreshold, setAlertThreshold] = useState(org.alert_auto_promote_threshold ?? 5);
  const [alertWindow, setAlertWindow] = useState(org.alert_auto_promote_window_minutes ?? 60);
  const [timezone, setTimezone] = useState(org.timezone ?? 'UTC');
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [alertSaveError, setAlertSaveError] = useState(null);
  const [alertSaved, setAlertSaved] = useState(false);

  const [systemRules, setSystemRules] = useState(null);
  const [loadingSystemRules, setLoadingSystemRules] = useState(false);
  const [muteTogglingId, setMuteTogglingId] = useState(null);

  const [systemSearchRules, setSystemSearchRules] = useState(null);
  const [loadingSystemSearchRules, setLoadingSystemSearchRules] = useState(false);
  const [searchMuteTogglingId, setSearchMuteTogglingId] = useState(null);

  async function loadInvitations() {
    if (invitations !== null) return;
    setLoadingInvites(true);
    try {
      const res = await api.get(`/api/security/organizations/${org.slug}/invite/`);
      setInvitations(res.data);
    } catch {
      setInvitations([]);
    } finally {
      setLoadingInvites(false);
    }
  }

  async function loadSystemRules() {
    if (systemRules !== null) return;
    setLoadingSystemRules(true);
    try {
      const res = await api.get(`/api/correlations/org-system-rules/?org=${org.slug}`);
      setSystemRules(res.data);
    } catch {
      setSystemRules([]);
    } finally {
      setLoadingSystemRules(false);
    }
  }

  async function handleToggleMute(rule) {
    setMuteTogglingId(rule.id);
    try {
      if (rule.muted) {
        await api.delete(`/api/correlations/org-system-rules/${rule.id}/mute/?org=${org.slug}`);
      } else {
        await api.post(`/api/correlations/org-system-rules/${rule.id}/mute/`, { org: org.slug });
      }
      setSystemRules(prev =>
        prev.map(r => (r.id === rule.id ? { ...r, muted: !r.muted } : r))
      );
    } catch {
      // leave state unchanged on error
    } finally {
      setMuteTogglingId(null);
    }
  }

  async function loadSystemSearchRules() {
    if (systemSearchRules !== null) return;
    setLoadingSystemSearchRules(true);
    try {
      const res = await api.get(`/api/correlations/org-system-search-rules/?org=${org.slug}`);
      setSystemSearchRules(res.data);
    } catch {
      setSystemSearchRules([]);
    } finally {
      setLoadingSystemSearchRules(false);
    }
  }

  async function handleToggleSearchMute(rule) {
    setSearchMuteTogglingId(rule.id);
    try {
      if (rule.muted) {
        await api.delete(`/api/correlations/org-system-search-rules/${rule.id}/mute/?org=${org.slug}`);
      } else {
        await api.post(`/api/correlations/org-system-search-rules/${rule.id}/mute/`, { org: org.slug });
      }
      setSystemSearchRules(prev =>
        prev.map(r => (r.id === rule.id ? { ...r, muted: !r.muted } : r))
      );
    } catch {
      // leave state unchanged on error
    } finally {
      setSearchMuteTogglingId(null);
    }
  }

  function handleToggle() {
    if (!expanded) {
      loadInvitations();
      loadSystemRules();
      loadSystemSearchRules();
    }
    setExpanded(v => !v);
  }

  function handleInviteCreated(inv) {
    setInvitations(prev => [inv, ...(prev ?? [])]);
  }

  async function handleSaveTriage(e) {
    e.preventDefault();
    setSavingTriage(true);
    setTriageSaveError(null);
    setTriageSaved(false);
    try {
      await api.patch(`/api/security/organizations/${org.slug}/`, {
        triage_prompt_context: triageContext || null,
      });
      setTriageSaved(true);
    } catch (err) {
      setTriageSaveError(err.response?.data?.triage_prompt_context?.[0] ?? 'Failed to save.');
    } finally {
      setSavingTriage(false);
    }
  }

  async function handleSaveAlertSettings(e) {
    e.preventDefault();
    setSavingAlerts(true);
    setAlertSaveError(null);
    setAlertSaved(false);
    try {
      await api.patch(`/api/security/organizations/${org.slug}/`, {
        alert_match_lookback_days: Number(alertLookback),
        alert_auto_promote_threshold: Number(alertThreshold),
        alert_auto_promote_window_minutes: Number(alertWindow),
        timezone: timezone.trim() || 'UTC',
      });
      setAlertSaved(true);
    } catch (err) {
      setAlertSaveError(err.response?.data?.timezone?.[0] ?? 'Failed to save alert settings.');
    } finally {
      setSavingAlerts(false);
    }
  }

  return (
    <>
      <tr className="border-b last:border-0">
        <td className="py-3 font-medium text-foreground">{org.name}</td>
        <td className="py-3 font-mono text-sm text-muted-foreground">{org.slug}</td>
        <td className="py-3 font-mono text-sm text-muted-foreground">{org.wazuh_group}</td>
        <td className="py-3 text-right">
          <div className="flex items-center justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowInviteDialog(true)}
              aria-label={`Invite user to ${org.name}`}
            >
              <UserPlus className="h-3.5 w-3.5 mr-1" />
              Invite
            </Button>
            <button
              onClick={handleToggle}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label={expanded ? `Collapse ${org.name} invitations` : `Expand ${org.name} invitations`}
            >
              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b last:border-0 bg-muted/30">
          <td colSpan={4} className="px-4 py-3 space-y-4">
            <div>
              {loadingInvites && <p className="text-sm text-muted-foreground">Loading invitations…</p>}
              {!loadingInvites && invitations !== null && invitations.length === 0 && (
                <p className="text-sm text-muted-foreground">No invitations yet.</p>
              )}
              {!loadingInvites && invitations && invitations.length > 0 && (
                <table className="w-full text-xs" aria-label={`Invitations for ${org.name}`}>
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-1 font-medium">Email</th>
                      <th className="pb-1 font-medium">Name</th>
                      <th className="pb-1 font-medium">Role</th>
                      <th className="pb-1 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invitations.map(inv => (
                      <tr key={inv.id} className="border-t border-border/50">
                        <td className="py-1.5 text-foreground">{inv.email}</td>
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
              )}
            </div>

            <form onSubmit={handleSaveTriage} className="space-y-2 border-t border-border/50 pt-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-foreground" htmlFor={`triage-context-${org.slug}`}>
                  Custom triage instructions
                </label>
                <span className={`text-xs ${triageContext.length > PROMPT_MAX ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {triageContext.length} / {PROMPT_MAX}
                </span>
              </div>
              <Textarea
                id={`triage-context-${org.slug}`}
                rows={4}
                placeholder="e.g. We are a healthcare provider. Treat PHI-related alerts as critical. Ignore SSH from 10.0.0.5 (jump host)."
                value={triageContext}
                onChange={e => { setTriageContext(e.target.value); setTriageSaved(false); }}
                disabled={savingTriage}
                className="text-xs resize-y"
              />
              {triageSaveError && <p className="text-xs text-destructive">{triageSaveError}</p>}
              {triageSaved && <p className="text-xs text-green-600 dark:text-green-400">Saved.</p>}
              <div className="flex justify-end">
                <Button
                  type="submit"
                  size="sm"
                  disabled={savingTriage || triageContext.length > PROMPT_MAX}
                >
                  {savingTriage ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </form>

            <form onSubmit={handleSaveAlertSettings} className="space-y-3 border-t border-border/50 pt-3 mt-3">
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider">Alert Settings</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`alert-lookback-${org.slug}`}>
                    Match lookback (days)
                  </label>
                  <input
                    id={`alert-lookback-${org.slug}`}
                    type="number"
                    min={1}
                    value={alertLookback}
                    onChange={e => { setAlertLookback(e.target.value); setAlertSaved(false); }}
                    disabled={savingAlerts}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`alert-threshold-${org.slug}`}>
                    Auto-promote threshold
                  </label>
                  <input
                    id={`alert-threshold-${org.slug}`}
                    type="number"
                    min={1}
                    value={alertThreshold}
                    onChange={e => { setAlertThreshold(e.target.value); setAlertSaved(false); }}
                    disabled={savingAlerts}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`alert-window-${org.slug}`}>
                    Promote window (min)
                  </label>
                  <input
                    id={`alert-window-${org.slug}`}
                    type="number"
                    min={1}
                    value={alertWindow}
                    onChange={e => { setAlertWindow(e.target.value); setAlertSaved(false); }}
                    disabled={savingAlerts}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`org-timezone-${org.slug}`}>
                    Timezone (IANA)
                  </label>
                  <input
                    id={`org-timezone-${org.slug}`}
                    type="text"
                    value={timezone}
                    onChange={e => { setTimezone(e.target.value); setAlertSaved(false); }}
                    disabled={savingAlerts}
                    placeholder="e.g. Europe/Amsterdam"
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm text-foreground"
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Used to evaluate Scheduled Search Rule time-of-day windows in this org's local time.
              </p>
              {alertSaveError && <p className="text-xs text-destructive">{alertSaveError}</p>}
              {alertSaved && <p className="text-xs text-green-600 dark:text-green-400">Saved.</p>}
              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={savingAlerts}>
                  {savingAlerts ? 'Saving…' : 'Save alert settings'}
                </Button>
              </div>
            </form>

            <div className="space-y-2 border-t border-border/50 pt-3 mt-3">
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider">System Rules</p>
              {loadingSystemRules && <p className="text-sm text-muted-foreground">Loading system rules…</p>}
              {!loadingSystemRules && systemRules !== null && systemRules.length === 0 && (
                <p className="text-sm text-muted-foreground">No system rules defined.</p>
              )}
              {!loadingSystemRules && systemRules && systemRules.length > 0 && (
                <table className="w-full text-xs" aria-label={`System rules for ${org.name}`}>
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-1 font-medium">Rule</th>
                      <th className="pb-1 font-medium">Severity</th>
                      <th className="pb-1 font-medium text-right">Mute for this org</th>
                    </tr>
                  </thead>
                  <tbody>
                    {systemRules.map(rule => (
                      <tr key={rule.id} className="border-t border-border/50">
                        <td className="py-1.5 text-foreground">{rule.name}</td>
                        <td className="py-1.5 text-muted-foreground capitalize">{rule.severity}</td>
                        <td className="py-1.5 text-right">
                          <Button
                            size="sm"
                            variant={rule.muted ? 'default' : 'outline'}
                            disabled={muteTogglingId === rule.id}
                            onClick={() => handleToggleMute(rule)}
                            aria-label={rule.muted ? `Unmute ${rule.name} for ${org.name}` : `Mute ${rule.name} for ${org.name}`}
                          >
                            {muteTogglingId === rule.id ? '…' : rule.muted ? 'Unmute' : 'Mute'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="space-y-2 border-t border-border/50 pt-3 mt-3">
              <p className="text-xs font-semibold text-foreground uppercase tracking-wider">System Search Rules</p>
              {loadingSystemSearchRules && <p className="text-sm text-muted-foreground">Loading system search rules…</p>}
              {!loadingSystemSearchRules && systemSearchRules !== null && systemSearchRules.length === 0 && (
                <p className="text-sm text-muted-foreground">No system search rules defined.</p>
              )}
              {!loadingSystemSearchRules && systemSearchRules && systemSearchRules.length > 0 && (
                <table className="w-full text-xs" aria-label={`System search rules for ${org.name}`}>
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-1 font-medium">Rule</th>
                      <th className="pb-1 font-medium">Severity</th>
                      <th className="pb-1 font-medium text-right">Mute for this org</th>
                    </tr>
                  </thead>
                  <tbody>
                    {systemSearchRules.map(rule => (
                      <tr key={rule.id} className="border-t border-border/50">
                        <td className="py-1.5 text-foreground">{rule.name}</td>
                        <td className="py-1.5 text-muted-foreground capitalize">{rule.severity}</td>
                        <td className="py-1.5 text-right">
                          <Button
                            size="sm"
                            variant={rule.muted ? 'default' : 'outline'}
                            disabled={searchMuteTogglingId === rule.id}
                            onClick={() => handleToggleSearchMute(rule)}
                            aria-label={rule.muted ? `Unmute ${rule.name} for ${org.name}` : `Mute ${rule.name} for ${org.name}`}
                          >
                            {searchMuteTogglingId === rule.id ? '…' : rule.muted ? 'Unmute' : 'Mute'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </td>
        </tr>
      )}

      {showInviteDialog && (
        <InviteDialog
          org={org}
          onClose={() => setShowInviteDialog(false)}
          onCreated={handleInviteCreated}
        />
      )}
    </>
  );
}

function OrgManagement() {
  const [orgs, setOrgs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    api
      .get('/api/security/organizations/')
      .then((res) => setOrgs(res.data))
      .catch(() => setError('Failed to load organisations.'))
      .finally(() => setIsLoading(false));
  }, []);

  function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setFormError(null);

    api
      .post('/api/security/organizations/', { name: name.trim() })
      .then((res) => {
        setOrgs((prev) => [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name)));
        setName('');
      })
      .catch((err) => {
        const detail = err.response?.data?.detail ?? 'Failed to create organisation.';
        setFormError(detail);
      })
      .finally(() => setSubmitting(false));
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Organisations</h1>
        <p className="text-sm text-muted-foreground">
          Manage customer organisations and their Wazuh agent groups.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Organisation</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="flex items-start gap-3">
            <div className="flex-1 space-y-1">
              <Input
                placeholder="Organisation name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
              />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
            </div>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? 'Creating…' : 'Create'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Organisations</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!isLoading && !error && orgs.length === 0 && (
            <p className="text-sm text-muted-foreground">No organisations yet.</p>
          )}
          {!isLoading && !error && orgs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">Slug</th>
                  <th className="pb-2 font-medium">Wazuh group</th>
                  <th className="pb-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {orgs.map((org) => (
                  <OrgRow key={org.id} org={org} />
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default OrgManagement;
