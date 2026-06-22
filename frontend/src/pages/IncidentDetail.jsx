import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import DelegationPanel from '../components/DelegationPanel';
import IncidentAttachments from '../components/IncidentAttachments';
import IncidentComments from '../components/IncidentComments';
import IncidentTimeline from '../components/IncidentTimeline';
import IncidentTasks from './IncidentTasks';
import SLAPill from '../components/SLAPill';
import { HelpTooltip } from '../components/ui/help-tooltip';
import CreateExceptionSlideOver from '../components/CreateExceptionSlideOver';
import ContactMessagesCard from '../components/ContactMessagesCard';
import ContactComposeModal from '../components/ContactComposeModal';
import IncidentAssistantDrawer from '../components/IncidentAssistantDrawer';
import LinkedIncidents from '../components/LinkedIncidents';

const TRIAGE_STATES = new Set(['new', 'triaged']);

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const TLP_CLASSES = {
  white: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  red:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const STATE_CLASSES = {
  new:          'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  triaged:      'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  in_progress:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  on_hold:      'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  needs_tuning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  pending_closure: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  resolved:     'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  closed:       'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

// States from which the resolve dropdown (Resolved / Needs tuning) is shown.
const RESOLVE_DROPDOWN_STATES = new Set(['in_progress', 'on_hold']);

const ALLOWED_TRANSITIONS = {
  new:          [{ state: 'triaged', label: 'Triage' }, { state: 'in_progress', label: 'Start work' }],
  triaged:      [{ state: 'in_progress', label: 'Start work' }, { state: 'on_hold', label: 'Put on hold' }],
  in_progress:  [{ state: 'on_hold', label: 'Put on hold' }, { state: 'pending_closure', label: 'Mark pending closure' }, { state: 'closed', label: 'Close' }],
  on_hold:      [{ state: 'in_progress', label: 'Resume' }, { state: 'pending_closure', label: 'Mark pending closure' }, { state: 'closed', label: 'Close' }],
  needs_tuning: [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  pending_closure: [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  resolved:     [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  closed:       [{ state: 'in_progress', label: 'Reopen' }],
};

const TRANSITION_BTN_CLASSES = {
  triaged:      'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  in_progress:  'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  on_hold:      'bg-amber-500 text-white hover:bg-amber-600 dark:bg-amber-600 dark:hover:bg-amber-500',
  needs_tuning: 'bg-amber-600 text-white hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600',
  pending_closure: 'bg-teal-600 text-white hover:bg-teal-700 dark:bg-teal-700 dark:hover:bg-teal-600',
  resolved:     'bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600',
  closed:       'bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600',
};

const CLOSURE_REASONS = [
  { value: 'resolved',       label: 'Resolved' },
  { value: 'false_positive', label: 'False Positive' },
  { value: 'no_impact',      label: 'No Impact' },
  { value: 'duplicate',      label: 'Duplicate' },
  { value: 'informational',  label: 'Informational' },
  { value: 'accepted_risk',  label: 'Accepted Risk' },
];

const TABS = [
  { key: 'details',       label: 'Details' },
  { key: 'timeline',      label: 'Timeline' },
  { key: 'attachments',   label: 'Attachments' },
  { key: 'tasks',         label: 'Tasks' },
  { key: 'delegations',   label: 'Delegations' },
  { key: 'assets',        label: 'Assets' },
  { key: 'iocs',          label: 'IOCs' },
  { key: 'contacts',      label: 'Contacts' },
  { key: 'linked_alerts', label: 'Linked Alerts' },
];

const EXCEPTION_STATUS_CLASSES = {
  pending:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  applied:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  disabled: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

function IncidentExceptionsSection({ displayId }) {
  const [exceptions, setExceptions] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.get('/api/exceptions/', { params: { incident: displayId } })
      .then(res => { setExceptions(Array.isArray(res.data) ? res.data : []); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [displayId]);

  if (!loaded || exceptions.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-3">
      <h2 className="text-base font-semibold text-foreground">Exceptions</h2>
      <ul className="divide-y divide-border">
        {exceptions.map(ex => (
          <li key={ex.id} className="flex items-center justify-between gap-3 py-2">
            <span className="text-sm text-foreground truncate flex-1">{ex.description || '—'}</span>
            <span className="text-xs text-muted-foreground shrink-0">{ex.scope}</span>
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0 ${EXCEPTION_STATUS_CLASSES[ex.status] ?? ''}`}>
              {ex.status}
            </span>
            <Link to="/exceptions" className="text-xs text-primary hover:underline shrink-0">
              View
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

const IOC_KIND_LABELS = { ip: 'IP Address', domain: 'Domain', url: 'URL', email: 'Email Address' };
const IOC_KIND_CLASSES = {
  ip:     'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  domain: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  url:    'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  email:  'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
};

function enrichmentScore(ioc) {
  const d = ioc.enrichment_data;
  if (!d || Object.keys(d).length === 0) return { state: 'pending' };
  if (ioc.kind === 'ip') {
    const ab = d.abuseipdb;
    if (!ab) return { state: 'pending' };
    if (ab.status === 'failed') return { state: 'failed', error: ab.error };
    const score = ab.abuse_confidence_score ?? 0;
    const color = score >= 75 ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                : score >= 25 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
                : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    return { state: 'done', label: `${score}/100`, color, detail: ab };
  }
  if (ioc.kind === 'domain' || ioc.kind === 'url') {
    const vt = d.virustotal;
    if (!vt) return { state: 'pending' };
    if (vt.status === 'failed') return { state: 'failed', error: vt.error };
    const mal = vt.malicious ?? 0;
    const total = vt.total ?? 0;
    const ratio = total > 0 ? mal / total : 0;
    const color = ratio >= 0.1 ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                : ratio > 0    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
                : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    return { state: 'done', label: `${mal}/${total}`, color, detail: vt };
  }
  return { state: 'pending' };
}

function EnrichmentBadge({ ioc }) {
  const s = enrichmentScore(ioc);
  if (s.state === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground">
        <svg className="h-2.5 w-2.5 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        pending
      </span>
    );
  }
  if (s.state === 'failed') {
    return (
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground">
        unavailable
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${s.color}`}>
      {s.label}
    </span>
  );
}

function EnrichmentDetail({ ioc }) {
  const s = enrichmentScore(ioc);
  if (s.state === 'pending') {
    return <p className="text-xs text-muted-foreground">Enrichment is pending…</p>;
  }
  if (s.state === 'failed') {
    return <p className="text-xs text-muted-foreground">Enrichment unavailable: {s.error || 'unknown error'}</p>;
  }
  const d = s.detail;
  if (ioc.kind === 'ip') {
    return (
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <dt className="text-muted-foreground">Abuse confidence</dt><dd className="text-foreground tabular-nums">{d.abuse_confidence_score}/100</dd>
        <dt className="text-muted-foreground">Total reports</dt><dd className="text-foreground tabular-nums">{d.total_reports ?? '—'}</dd>
        <dt className="text-muted-foreground">Country</dt><dd className="text-foreground">{d.country_code ?? '—'}</dd>
        <dt className="text-muted-foreground">Usage type</dt><dd className="text-foreground">{d.usage_type ?? '—'}</dd>
      </dl>
    );
  }
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
      <dt className="text-muted-foreground">Malicious engines</dt><dd className="text-foreground tabular-nums">{d.malicious ?? '—'}</dd>
      <dt className="text-muted-foreground">Suspicious engines</dt><dd className="text-foreground tabular-nums">{d.suspicious ?? '—'}</dd>
      <dt className="text-muted-foreground">Total engines</dt><dd className="text-foreground tabular-nums">{d.total ?? '—'}</dd>
    </dl>
  );
}

function IOCRow({ ioc, kindClass }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded border border-border bg-background">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <button
          onClick={() => setExpanded(e => !e)}
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          <svg className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
        <span className={`font-mono text-xs ${kindClass}`}>{ioc.value}</span>
        <div className="ml-auto">
          <EnrichmentBadge ioc={ioc} />
        </div>
      </div>
      {expanded && (
        <div className="border-t border-border px-3 py-2">
          <EnrichmentDetail ioc={ioc} />
        </div>
      )}
    </div>
  );
}

function IOCSection({ iocs }) {
  const grouped = iocs.reduce((acc, ioc) => {
    if (!acc[ioc.kind]) acc[ioc.kind] = [];
    acc[ioc.kind].push(ioc);
    return acc;
  }, {});

  const kinds = ['ip', 'domain', 'url', 'email'].filter(k => grouped[k]?.length);

  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-4">
      <h2 className="text-base font-semibold text-foreground">Indicators of Compromise</h2>
      {kinds.length === 0 ? (
        <p className="text-sm text-muted-foreground">No IOCs were extracted from this incident.</p>
      ) : (
        <div className="space-y-4">
          {kinds.map(kind => (
            <div key={kind} className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {IOC_KIND_LABELS[kind]}
              </p>
              <div className="space-y-1">
                {grouped[kind].map(ioc => (
                  <IOCRow key={ioc.id} ioc={ioc} kindClass={IOC_KIND_CLASSES[kind]} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function IncidentContactsPanel({ displayId, orgSlug }) {
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allContacts, setAllContacts] = useState([]);
  const [addSearch, setAddSearch] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [composingFor, setComposingFor] = useState(null);

  function reload() {
    return api.get(`/api/incidents/${displayId}/contacts/`).then(r => setContacts(r.data));
  }

  useEffect(() => {
    reload().finally(() => setLoading(false));
    api.get('/api/contacts/').then(r => setAllContacts(r.data)).catch(() => {});
  }, [displayId]); // eslint-disable-line react-hooks/exhaustive-deps

  const linkedIds = new Set(contacts.map(c => c.contact_id));
  const filteredAdd = allContacts.filter(c =>
    !linkedIds.has(c.id) &&
    (c.name.toLowerCase().includes(addSearch.toLowerCase()) ||
     c.email.toLowerCase().includes(addSearch.toLowerCase()))
  );

  async function addContact(contactId) {
    setAdding(true);
    setAddError(null);
    try {
      await api.post(`/api/incidents/${displayId}/contacts/`, { contact_id: contactId });
      await reload();
      setAddSearch('');
    } catch (err) {
      setAddError(err.response?.data?.detail || 'Failed to add contact.');
    } finally {
      setAdding(false);
    }
  }

  async function removeContact(rowId) {
    try {
      await api.delete(`/api/incidents/${displayId}/contacts/${rowId}/`);
      setContacts(prev => prev.filter(c => c.id !== rowId));
    } catch {
      // silently ignore
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-6 space-y-3">
        <h2 className="text-base font-semibold text-foreground">Contacts</h2>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : contacts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No contacts linked to this incident.</p>
        ) : (
          <div className="divide-y divide-border">
            {contacts.map(c => (
              <div key={c.id} className="py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">{c.name}</p>
                    <p className="text-xs text-muted-foreground">{c.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setComposingFor(c)}
                      className="text-xs text-blue-500 hover:text-blue-700"
                    >
                      Message
                    </button>
                    <button
                      onClick={() => removeContact(c.id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-foreground">Add Contact</h3>
        <input
          type="search"
          placeholder="Search contacts…"
          value={addSearch}
          onChange={e => setAddSearch(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {addSearch && filteredAdd.length > 0 && (
          <ul className="rounded-md border border-border bg-background divide-y divide-border max-h-48 overflow-y-auto">
            {filteredAdd.slice(0, 8).map(c => (
              <li key={c.id}>
                <button
                  onClick={() => addContact(c.id)}
                  disabled={adding}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-accent/50 text-foreground disabled:opacity-50"
                >
                  <span className="font-medium">{c.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{c.email}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {addSearch && filteredAdd.length === 0 && (
          <p className="text-xs text-muted-foreground">No unlinked contacts match.</p>
        )}
        {addError && <p className="text-xs text-red-600">{addError}</p>}
      </div>

      {composingFor && (
        <ContactComposeModal
          displayId={displayId}
          contact={composingFor}
          onClose={() => setComposingFor(null)}
          onSent={() => setComposingFor(null)}
        />
      )}
    </div>
  );
}

function IncidentAssetsPanel({ displayId, isStaff, orgSlug }) {
  const [assets, setAssets] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchDone, setSearchDone] = useState(false);
  const [linking, setLinking] = useState(false);
  const [unlinking, setUnlinking] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createAgentName, setCreateAgentName] = useState('');
  const [createIp, setCreateIp] = useState('');
  const [creating, setCreating] = useState(false);

  const loadAssets = useCallback(() => {
    api.get(`/api/incidents/${displayId}/`)
      .then(res => { setAssets(res.data.assets ?? []); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [displayId]);

  useEffect(() => { loadAssets(); }, [loadAssets]);

  useEffect(() => {
    setSearchDone(false);
    setShowCreateForm(false);
    if (!searchQ.trim()) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get('/api/assets/', { params: { org: orgSlug, q: searchQ } });
        const existingIds = new Set(assets.map(a => a.asset.id));
        setSearchResults((res.data ?? []).filter(a => !existingIds.has(a.id)));
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
        setSearchDone(true);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQ, orgSlug, assets]);

  async function handleLink(assetId) {
    setLinking(true);
    setError(null);
    try {
      await api.post(`/api/incidents/${displayId}/assets/`, { asset: assetId });
      setSearchQ('');
      setSearchResults([]);
      setSearchDone(false);
      setShowCreateForm(false);
      loadAssets();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to link asset.');
    } finally {
      setLinking(false);
    }
  }

  async function handleUnlink(assetId) {
    setUnlinking(assetId);
    setError(null);
    try {
      await api.delete(`/api/incidents/${displayId}/assets/${assetId}/`);
      loadAssets();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to unlink asset.');
    } finally {
      setUnlinking(null);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!createAgentName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const createRes = await api.post('/api/assets/', {
        kind: 'host',
        organization: orgSlug,
        name: createName.trim() || createAgentName.trim(),
        agent_name: createAgentName.trim(),
        ip_address: createIp.trim() || undefined,
      });
      await handleLink(createRes.data.id);
      setCreateName('');
      setCreateAgentName('');
      setCreateIp('');
      setShowCreateForm(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create asset.');
    } finally {
      setCreating(false);
    }
  }

  function openCreateForm() {
    setCreateAgentName(searchQ.trim());
    setCreateName(searchQ.trim());
    setCreateIp('');
    setShowCreateForm(true);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Affected assets</h2>
        <span className="text-xs text-muted-foreground">{assets.length} linked</span>
      </div>

      {loaded && assets.length === 0 && (
        <p className="text-sm text-muted-foreground">No assets linked to this incident.</p>
      )}

      {assets.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {assets.map(({ id, asset, added_by, added_by_username, added_at }) => (
            <li key={id} className="flex items-center gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium text-foreground">{asset.name}</span>
                {asset.agent_name && asset.agent_name !== asset.name && (
                  <span className="ml-2 text-xs text-muted-foreground font-mono">{asset.agent_name}</span>
                )}
                {asset.ip_address && (
                  <span className="ml-2 text-xs text-muted-foreground">{asset.ip_address}</span>
                )}
                {asset.route_fqdn && (
                  <span className="ml-2 text-xs text-muted-foreground">{asset.route_fqdn}</span>
                )}
              </div>
              <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground shrink-0">
                {asset.kind}
              </span>
              {added_by === null ? (
                <span className="inline-flex items-center rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 px-2 py-0.5 text-xs shrink-0">
                  auto-detected
                </span>
              ) : (
                <span className="text-xs text-muted-foreground shrink-0">
                  {added_by_username} · {added_at ? new Date(added_at).toLocaleDateString() : ''}
                </span>
              )}
              {isStaff && (
                <button
                  onClick={() => handleUnlink(asset.id)}
                  disabled={unlinking === asset.id}
                  className="text-xs text-muted-foreground hover:text-red-600 disabled:opacity-50 shrink-0"
                  aria-label={`Unlink ${asset.name}`}
                >
                  {unlinking === asset.id ? '…' : 'Unlink'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isStaff && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Link an asset
          </label>
          <input
            type="search"
            placeholder="Search assets by name…"
            value={searchQ}
            onChange={e => { setSearchQ(e.target.value); setShowCreateForm(false); }}
            className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
          {searchResults.length > 0 && (
            <ul className="rounded-md border border-border bg-card divide-y divide-border">
              {searchResults.map(a => (
                <li key={a.id} className="flex items-center gap-2 px-3 py-2">
                  <span className="flex-1 text-sm text-foreground">{a.name}</span>
                  <span className="text-xs text-muted-foreground">{a.kind}</span>
                  <button
                    onClick={() => handleLink(a.id)}
                    disabled={linking}
                    className="text-xs text-primary hover:underline disabled:opacity-50"
                  >
                    {linking ? 'Linking…' : 'Link'}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {searchDone && !searching && searchResults.length === 0 && !showCreateForm && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>No matching assets found.</span>
              <button
                onClick={openCreateForm}
                className="text-primary hover:underline font-medium"
              >
                Create and link "{searchQ.trim()}"
              </button>
            </div>
          )}
          {showCreateForm && (
            <form
              onSubmit={handleCreate}
              className="rounded-md border border-border bg-card p-4 space-y-3"
            >
              <p className="text-xs font-medium text-foreground">New host asset</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground" htmlFor="asset-agent-name">
                    Agent / hostname <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="asset-agent-name"
                    type="text"
                    required
                    value={createAgentName}
                    onChange={e => setCreateAgentName(e.target.value)}
                    className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="e.g. web-prod-01"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground" htmlFor="asset-name">
                    Display name
                  </label>
                  <input
                    id="asset-name"
                    type="text"
                    value={createName}
                    onChange={e => setCreateName(e.target.value)}
                    placeholder="Defaults to agent name"
                    className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground" htmlFor="asset-ip">
                    IP address
                  </label>
                  <input
                    id="asset-ip"
                    type="text"
                    value={createIp}
                    onChange={e => setCreateIp(e.target.value)}
                    placeholder="Optional"
                    className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !createAgentName.trim()}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {creating ? 'Creating…' : 'Create and link'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

function TriageDebugModal({ displayId, onClose }) {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [userPayload, setUserPayload] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [rawResponse, setRawResponse] = useState(null);
  const [parsedResult, setParsedResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/api/incidents/${displayId}/triage/debug/`)
      .then(res => {
        setSystemPrompt(res.data.system_prompt);
        setUserPayload(res.data.user_payload);
      })
      .catch(() => setError('Failed to load triage prompt.'))
      .finally(() => setLoading(false));
  }, [displayId]);

  async function handleSend() {
    setSending(true);
    setError(null);
    setRawResponse(null);
    setParsedResult(null);
    try {
      const res = await api.post(`/api/incidents/${displayId}/triage/debug/`, {
        system_prompt: systemPrompt,
        user_payload: userPayload,
      });
      setRawResponse(res.data.raw_response);
      setParsedResult(res.data.result);
    } catch (err) {
      setError(err.response?.data?.detail || 'LLM request failed.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Debug Triage</h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent">
            ✕
          </button>
        </div>
        {loading ? (
          <p className="px-6 py-8 text-sm text-muted-foreground">Loading prompt…</p>
        ) : (
          <div className="space-y-4 px-6 py-4">
            {error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
            )}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">System Prompt</label>
              <textarea
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
                rows={10}
                className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-y"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">User Payload (JSON)</label>
              <textarea
                value={userPayload}
                onChange={e => setUserPayload(e.target.value)}
                rows={8}
                className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-y"
              />
            </div>
            <div className="flex justify-end">
              <button
                onClick={handleSend}
                disabled={sending}
                className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50 transition-colors"
              >
                {sending ? 'Sending…' : 'Send to LLM'}
              </button>
            </div>
            {rawResponse !== null && (
              <>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Raw LLM Response</label>
                  <pre className="w-full rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs text-foreground overflow-x-auto whitespace-pre-wrap">{rawResponse}</pre>
                </div>
                {parsedResult && (
                  <div className="rounded-md border border-border bg-muted/50 px-4 py-3 space-y-1">
                    <p className="text-xs font-medium text-muted-foreground">Parsed result</p>
                    <p className="text-sm text-foreground"><span className="font-medium">Severity:</span> {parsedResult.severity_recommendation}</p>
                    <p className="text-sm text-foreground"><span className="font-medium">Action:</span> {parsedResult.primary_action}{parsedResult.secondary_action ? ` / ${parsedResult.secondary_action}` : ''}</p>
                    <p className="text-sm text-foreground"><span className="font-medium">FP confidence:</span> {(parsedResult.false_positive_confidence * 100).toFixed(0)}%</p>
                    <p className="text-sm text-foreground"><span className="font-medium">Summary:</span> {parsedResult.summary}</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TriageDropdown({ onRunTriage, onDebugTriage, disabled, label }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className="flex rounded-md overflow-hidden">
        <button
          onClick={() => { setOpen(false); onRunTriage(); }}
          disabled={disabled}
          className="rounded-none border border-violet-400 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-violet-600 dark:bg-violet-900/20 dark:text-violet-400 dark:hover:bg-violet-900/40"
        >
          {label}
        </button>
        <button
          onClick={() => setOpen(o => !o)}
          disabled={disabled}
          aria-label="Triage options"
          className="border border-l-0 border-violet-400 bg-violet-50 px-2 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-violet-600 dark:bg-violet-900/20 dark:text-violet-400 dark:hover:bg-violet-900/40"
        >
          ▾
        </button>
      </div>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-10 w-36 rounded-md border border-border bg-card shadow-lg">
          <button
            onClick={() => { setOpen(false); onDebugTriage(); }}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent rounded-md"
          >
            Debug Triage
          </button>
        </div>
      )}
    </div>
  );
}

function ResolveDropdown({ onResolve, onNeedsTuning, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className="flex rounded-md overflow-hidden">
        <button
          onClick={() => { setOpen(false); onResolve(); }}
          disabled={disabled}
          className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600 px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors"
        >
          Mark resolved
        </button>
        <button
          onClick={() => setOpen(o => !o)}
          disabled={disabled}
          aria-label="More resolution options"
          className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600 px-2 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors border-l border-green-500 dark:border-green-600"
        >
          ▾
        </button>
      </div>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-10 w-44 rounded-md border border-border bg-card shadow-lg">
          <button
            onClick={() => { setOpen(false); onResolve(); }}
            disabled={disabled}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50 rounded-t-md"
          >
            Resolved
          </button>
          <button
            onClick={() => { setOpen(false); onNeedsTuning(); }}
            disabled={disabled}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50 rounded-b-md"
          >
            Needs tuning
          </button>
        </div>
      )}
    </div>
  );
}

// Short, plain-language descriptions for the incident header fields, surfaced
// via the reusable HelpTooltip (see issue #589).
const FIELD_HELP = {
  State: 'Where the incident is in its lifecycle (e.g. New → Triaged → In progress → On hold → Pending closure → Resolved/Closed).',
  SLA: 'Service Level Agreement: the time target for responding to / resolving this incident. The pill shows time remaining or how overdue it is.',
  Severity: 'How serious the incident is, based on impact and urgency. Drives prioritisation.',
  Source: 'Where the incident originated (e.g. an alert, a manual report, or an integration).',
  TLP: 'Traffic Light Protocol: how widely this information may be shared (Clear / Green / Amber / Red).',
  PAP: 'Permissible Actions Protocol: what active actions an analyst may take on the related indicators without risking tipping off an adversary (Clear / Green / Amber / Red).',
};

function FieldLabel({ label, help }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
      {label}
      {help && <HelpTooltip label={label} text={help} />}
    </span>
  );
}

function Badge({ label, value, badgeClass, help }) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} help={help} />
      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
        {value}
      </span>
    </div>
  );
}

function Field({ label, value, help }) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} help={help} />
      <span className="text-sm text-foreground">{value || '—'}</span>
    </div>
  );
}

function InlineSelect({ label, value, options, colorClasses, onChange, saving, help }) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label={label} help={help} />
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={saving}
        aria-label={label}
        className={`w-fit cursor-pointer rounded-full border-0 px-2 py-0.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${colorClasses[value] ?? ''}`}
      >
        {options.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    </div>
  );
}

function IncidentSearchSelect({ currentDisplayId, value, onChange }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get('/api/incidents/', { params: { q: query, limit: 20 } });
        const items = Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        setResults(items.filter(i => i.display_id !== currentDisplayId));
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query, currentDisplayId]);

  const selected = value;

  return (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium text-foreground">Canonical incident</label>
      {selected ? (
        <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span className="font-mono text-xs text-muted-foreground mr-2">{selected.display_id}</span>
          <span className="flex-1 truncate text-foreground">{selected.title}</span>
          <button onClick={() => onChange(null)} className="ml-2 text-muted-foreground hover:text-foreground text-xs">✕</button>
        </div>
      ) : (
        <>
          <input
            type="text"
            placeholder="Search by title…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {(results.length > 0 || searching) && (
            <div className="rounded-md border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
              {searching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
              {results.map(inc => (
                <button
                  key={inc.id}
                  type="button"
                  onClick={() => { onChange(inc); setQuery(''); setResults([]); }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center gap-2"
                >
                  <span className="font-mono text-xs text-muted-foreground shrink-0">{inc.display_id}</span>
                  <span className="flex-1 truncate text-foreground">{inc.title}</span>
                  {inc.state === 'closed' && (
                    <span className="text-xs text-amber-600 dark:text-amber-400 shrink-0">closed</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ClosureReasonDialog({ onConfirm, onCancel, transitioning, incidentDisplayId }) {
  const [reason, setReason] = useState('');
  const [duplicateOf, setDuplicateOf] = useState(null);
  const canConfirm = reason && (reason !== 'duplicate' || duplicateOf);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Close incident</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="closure-reason">
            Closure reason
          </label>
          <select
            id="closure-reason"
            value={reason}
            onChange={e => { setReason(e.target.value); setDuplicateOf(null); }}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a reason…</option>
            {CLOSURE_REASONS.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        {reason === 'duplicate' && (
          <IncidentSearchSelect
            currentDisplayId={incidentDisplayId}
            value={duplicateOf}
            onChange={setDuplicateOf}
          />
        )}
        {reason === 'duplicate' && duplicateOf?.state === 'closed' && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Warning: the selected incident is already closed.
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={transitioning}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => canConfirm && onConfirm(reason, duplicateOf?.id ?? null)}
            disabled={!canConfirm || transitioning}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {transitioning ? 'Closing…' : 'Close incident'}
          </button>
        </div>
      </div>
    </div>
  );
}

function TransferDialog({ onConfirm, onCancel, transferring, staffUsers, isInitialAssignment }) {
  const [selectedId, setSelectedId] = useState('');
  const title = isInitialAssignment ? 'Assign incident' : 'Transfer incident';
  const confirmLabel = transferring
    ? (isInitialAssignment ? 'Assigning…' : 'Transferring…')
    : (isInitialAssignment ? 'Confirm assignment' : 'Confirm transfer');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="transfer-assignee">
            New assignee
          </label>
          <select
            id="transfer-assignee"
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a staff user…</option>
            {staffUsers.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={transferring}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => selectedId && onConfirm(Number(selectedId))}
            disabled={!selectedId || transferring}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function ChangeOrgDialog({ onConfirm, onCancel, changing, orgs, currentOrgSlug }) {
  const [selectedSlug, setSelectedSlug] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Change organisation</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="change-org">
            New organisation
          </label>
          <select
            id="change-org"
            value={selectedSlug}
            onChange={e => setSelectedSlug(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select an organisation…</option>
            {orgs.filter(o => o.slug !== currentOrgSlug).map(o => (
              <option key={o.slug} value={o.slug}>{o.name}</option>
            ))}
          </select>
        </div>
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          Linked alerts will move to the new organisation. The incident's linked assets
          will be detached — assets are per-tenant and are not migrated.
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={changing}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => selectedSlug && onConfirm(selectedSlug)}
            disabled={!selectedSlug || changing}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {changing ? 'Changing…' : 'Confirm change'}
          </button>
        </div>
      </div>
    </div>
  );
}

function SubjectDropdown({ incident, subjects, onSubjectChange, saving }) {
  const locked = !TRIAGE_STATES.has(incident.state);
  const value = incident.subject ?? '';

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Subject</span>
      <div title={locked ? 'Subject is locked once the incident leaves triage.' : undefined}>
        <select
          value={value}
          onChange={e => !locked && onSubjectChange(e.target.value ? Number(e.target.value) : null)}
          disabled={locked || saving}
          aria-label="Subject"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">— None —</option>
          {subjects.filter(s => !s.archived || s.id === incident.subject).map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function IncidentDetail() {
  const { displayId } = useParams();
  const { user } = useAuth();
  const [incident, setIncident]           = useState(null);
  const [subjects, setSubjects]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const [transitionError, setTransitionError] = useState(null);
  const [pendingClose, setPendingClose]   = useState(false);
  const [savingSubject, setSavingSubject] = useState(false);
  const [subjectError, setSubjectError]   = useState(null);
  const [tasksRefreshKey, setTasksRefreshKey] = useState(0);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const [commentsRefreshKey, setCommentsRefreshKey] = useState(0);
  const [showTransferDialog, setShowTransferDialog] = useState(false);
  const [staffUsers, setStaffUsers]       = useState([]);
  const [transferring, setTransferring]   = useState(false);
  const [transferError, setTransferError] = useState(null);
  const [showChangeOrgDialog, setShowChangeOrgDialog] = useState(false);
  const [orgs, setOrgs]                   = useState([]);
  const [changingOrg, setChangingOrg]     = useState(false);
  const [changeOrgError, setChangeOrgError] = useState(null);
  const [savingBadge, setSavingBadge]     = useState(false);
  const [badgeError, setBadgeError]       = useState(null);
  const [activeTab, setActiveTab]         = useState('details');
  const [showExceptionSlideOver, setShowExceptionSlideOver] = useState(false);
  const [triaging, setTriaging]           = useState(false);
  const [triageQueued, setTriageQueued]   = useState(false);
  const [triageError, setTriageError]     = useState(null);
  const [showDebugModal, setShowDebugModal] = useState(false);
  const [showAssistant, setShowAssistant] = useState(false);
  const pollRef = useRef(null);
  const incidentRef = useRef(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [incRes, subRes] = await Promise.all([
          api.get(`/api/incidents/${displayId}/`),
          api.get('/api/subjects/'),
        ]);
        setIncident(incRes.data);
        setSubjects(subRes.data);
      } catch (err) {
        setError(err.response?.status === 404 ? 'Incident not found.' : 'Failed to load incident.');
      } finally {
        setLoading(false);
      }
    }
    load();

    if (pollRef.current) clearTimeout(pollRef.current);

    function schedulePoll() {
      const delay = incidentRef.current?.triage_running ? 5000 : 30000;
      pollRef.current = setTimeout(() => {
        if (document.visibilityState !== 'hidden') {
          api.get(`/api/incidents/${displayId}/`)
            .then(res => {
              setIncident(prev => {
                if (!prev) return prev;
                if (res.data.updated_at !== prev.updated_at) {
                  setTasksRefreshKey(k => k + 1);
                  setTimelineRefreshKey(k => k + 1);
                  setCommentsRefreshKey(k => k + 1);
                }
                incidentRef.current = res.data;
                return res.data;
              });
            })
            .catch(() => {})
            .finally(schedulePoll);
        } else {
          schedulePoll();
        }
      }, delay);
    }

    schedulePoll();
    return () => clearTimeout(pollRef.current);
  }, [displayId]);

  useEffect(() => { incidentRef.current = incident; }, [incident]);

  async function handleOpenTransfer() {
    if (staffUsers.length === 0) {
      try {
        const res = await api.get('/api/incidents/staff-users/');
        setStaffUsers(res.data);
      } catch {
        setTransferError('Failed to load staff users.');
        return;
      }
    }
    setTransferError(null);
    setShowTransferDialog(true);
  }

  async function handleTransfer(assigneeId) {
    setTransferring(true);
    setTransferError(null);
    try {
      const res = await api.post(`/api/incidents/${displayId}/transfer/`, { assignee_id: assigneeId });
      setIncident(res.data);
      setShowTransferDialog(false);
    } catch (err) {
      setTransferError(err.response?.data?.detail || 'Transfer failed.');
    } finally {
      setTransferring(false);
    }
  }

  async function handleOpenChangeOrg() {
    if (orgs.length === 0) {
      try {
        const res = await api.get('/api/security/organizations/');
        setOrgs(res.data);
      } catch {
        setChangeOrgError('Failed to load organisations.');
        return;
      }
    }
    setChangeOrgError(null);
    setShowChangeOrgDialog(true);
  }

  async function handleChangeOrg(slug) {
    setChangingOrg(true);
    setChangeOrgError(null);
    try {
      const res = await api.post(`/api/incidents/${displayId}/change-org/`, { organization: slug });
      setIncident(res.data);
      setShowChangeOrgDialog(false);
      setTimelineRefreshKey(k => k + 1);
    } catch (err) {
      setChangeOrgError(err.response?.data?.detail || 'Failed to change organisation.');
    } finally {
      setChangingOrg(false);
    }
  }

  const handleSubjectChange = useCallback(async (subjectId) => {
    setSavingSubject(true);
    setSubjectError(null);
    try {
      const res = await api.patch(`/api/incidents/${displayId}/`, { subject: subjectId });
      setIncident(res.data);
      setTasksRefreshKey(k => k + 1);
    } catch (err) {
      setSubjectError(err.response?.data?.detail || 'Failed to update subject.');
    } finally {
      setSavingSubject(false);
    }
  }, [displayId]);

  const handleBadgeChange = useCallback(async (field, value) => {
    setSavingBadge(true);
    setBadgeError(null);
    try {
      const res = await api.patch(`/api/incidents/${displayId}/`, { [field]: value });
      setIncident(res.data);
    } catch (err) {
      setBadgeError(err.response?.data?.detail || `Failed to update ${field}.`);
    } finally {
      setSavingBadge(false);
    }
  }, [displayId]);

  async function handleTransition(targetState, closureReason = undefined, duplicateOfId = null, assigneeId = undefined) {
    setTransitioning(true);
    setTransitionError(null);
    try {
      const payload = { state: targetState };
      if (closureReason) payload.closure_reason = closureReason;
      if (duplicateOfId) payload.duplicate_of = duplicateOfId;
      if (assigneeId !== undefined) payload.assignee_id = assigneeId;
      const res = await api.post(`/api/incidents/${displayId}/transition/`, payload);
      setIncident(res.data);
    } catch (err) {
      setTransitionError(err.response?.data?.detail || 'Transition failed.');
    } finally {
      setTransitioning(false);
      setPendingClose(false);
    }
  }

  async function handleTriage() {
    setTriaging(true);
    setTriageError(null);
    try {
      await api.post(`/api/incidents/${displayId}/triage/`);
      setTriageQueued(true);
    } catch (err) {
      setTriageError(err.response?.data?.detail || 'Triage request failed.');
    } finally {
      setTriaging(false);
    }
  }

  const START_WORK_STATES = new Set(['new', 'triaged']);

  function handleActionClick(targetState) {
    if (targetState === 'closed') {
      setPendingClose(true);
    } else {
      const assigneeId = targetState === 'in_progress' && START_WORK_STATES.has(incident.state)
        ? user?.id
        : undefined;
      handleTransition(targetState, undefined, null, assigneeId);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;
  if (error)   return <p className="text-sm text-red-600 p-6">{error}</p>;
  if (!incident) return null;

  const nextStates = ALLOWED_TRANSITIONS[incident.state] ?? [];

  return (
    <div className="space-y-6 p-6">
      {pendingClose && (
        <ClosureReasonDialog
          transitioning={transitioning}
          incidentDisplayId={displayId}
          onConfirm={(reason, duplicateOfId) => handleTransition('closed', reason, duplicateOfId)}
          onCancel={() => setPendingClose(false)}
        />
      )}

      {showTransferDialog && (
        <TransferDialog
          staffUsers={staffUsers}
          transferring={transferring}
          onConfirm={handleTransfer}
          onCancel={() => setShowTransferDialog(false)}
          isInitialAssignment={!incident.assignee_username}
        />
      )}

      {showChangeOrgDialog && (
        <ChangeOrgDialog
          orgs={orgs}
          changing={changingOrg}
          currentOrgSlug={incident.org_slug}
          onConfirm={handleChangeOrg}
          onCancel={() => setShowChangeOrgDialog(false)}
        />
      )}

      <CreateExceptionSlideOver
        open={showExceptionSlideOver}
        onClose={() => setShowExceptionSlideOver(false)}
        incident={incident}
      />

      {showDebugModal && (
        <TriageDebugModal
          displayId={displayId}
          onClose={() => setShowDebugModal(false)}
        />
      )}

      {showAssistant && (
        <IncidentAssistantDrawer
          displayId={displayId}
          onClose={() => setShowAssistant(false)}
          onActionConfirmed={() => {
            api.get(`/api/incidents/${displayId}/`).then(r => setIncident(r.data)).catch(() => {});
            setTasksRefreshKey(k => k + 1);
            setTimelineRefreshKey(k => k + 1);
            setCommentsRefreshKey(k => k + 1);
          }}
        />
      )}

      <div className="flex items-center gap-3">
        <Link to="/incidents" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Incidents
        </Link>
      </div>

      {/* ── Header card: title + actions ── */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0">
            <p className="font-mono text-xs text-muted-foreground">{incident.display_id}</p>
            <h1 className="mt-1 text-2xl font-semibold text-foreground">{incident.title}</h1>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            {user?.is_staff && nextStates.map(({ state, label }) => (
              <button
                key={state}
                onClick={() => handleActionClick(state)}
                disabled={transitioning}
                className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors ${TRANSITION_BTN_CLASSES[state] ?? 'border border-border bg-background text-foreground hover:bg-accent'}`}
              >
                {label}
              </button>
            ))}
            {user?.is_staff && RESOLVE_DROPDOWN_STATES.has(incident.state) && (
              <ResolveDropdown
                // "Mark resolved" closes the incident in one click with the implicit
                // closure reason "resolved" (#489) — no separate close step or prompt.
                onResolve={() => handleTransition('closed', 'resolved')}
                onNeedsTuning={() => handleActionClick('needs_tuning')}
                disabled={transitioning}
              />
            )}
            {user?.is_staff && incident.state !== 'closed' && (
              <button
                onClick={handleOpenTransfer}
                disabled={transitioning || transferring}
                className="rounded-md border border-slate-400 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {incident.assignee_username ? 'Transfer' : 'Assign'}
              </button>
            )}
            {user?.is_staff && TRIAGE_STATES.has(incident.state) && (
              <button
                onClick={handleOpenChangeOrg}
                disabled={transitioning || changingOrg}
                className="rounded-md border border-slate-400 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                Change Org
              </button>
            )}
            {user?.is_staff && incident.source_kind === 'wazuh_event' && incident.state !== 'closed' && (
              <button
                onClick={() => setShowExceptionSlideOver(true)}
                className="rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors dark:border-amber-600 dark:bg-amber-900/20 dark:text-amber-400 dark:hover:bg-amber-900/40"
              >
                Create Exception
              </button>
            )}
            {user?.is_staff && incident.state !== 'closed' && (
              <TriageDropdown
                onRunTriage={handleTriage}
                onDebugTriage={() => setShowDebugModal(true)}
                disabled={triaging || triageQueued || incident.triage_running || transitioning}
                label={triaging ? 'Triaging…' : (triageQueued || incident.triage_running) ? 'Triage running…' : 'Run Triage'}
              />
            )}
            {user?.is_staff && (
              <button
                onClick={() => setShowAssistant(true)}
                className="rounded-md border border-indigo-400 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-100 transition-colors dark:border-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400 dark:hover:bg-indigo-900/40"
              >
                Ask AI
              </button>
            )}
          </div>
        </div>
        {transitionError && <p className="text-sm text-red-600">{transitionError}</p>}
        {transferError   && <p className="text-sm text-red-600">{transferError}</p>}
        {changeOrgError  && <p className="text-sm text-red-600">{changeOrgError}</p>}
        {badgeError      && <p className="text-sm text-red-600">{badgeError}</p>}
        {triageError     && <p className="text-sm text-red-600">{triageError}</p>}
      </div>

      {/* ── Triage-running banner ── */}
      {(triageQueued || incident.triage_running) && (
        <div className="flex items-center gap-3 rounded-lg border border-violet-300 bg-violet-50 dark:border-violet-700 dark:bg-violet-950/30 px-4 py-3 text-sm text-violet-800 dark:text-violet-300">
          <svg
            className="h-4 w-4 shrink-0 animate-spin text-violet-600 dark:text-violet-400"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="font-medium">Automated triage is running</span>
          {incident.triage_started_at && (
            <span className="text-violet-600 dark:text-violet-400">
              · started {new Date(incident.triage_started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <span className="ml-auto text-xs text-violet-500 dark:text-violet-500">
            This page polls automatically — results will appear when triage completes.
          </span>
        </div>
      )}

      {/* ── Tabbed content ── */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="flex overflow-x-auto border-b border-border no-scrollbar">
          {(() => {
            const tabCounts = {
              attachments:   incident.attachment_count   ?? 0,
              tasks:         incident.task_count         ?? 0,
              contacts:      incident.contact_count      ?? 0,
              iocs:          incident.iocs?.length       ?? 0,
              assets:        incident.assets?.length     ?? 0,
              linked_alerts: incident.linked_alert_count ?? 0,
            };
            return TABS.map(tab => {
              const count = tabCounts[tab.key] ?? 0;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`shrink-0 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors inline-flex items-center gap-1.5 ${
                    activeTab === tab.key
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tab.label}
                  {count > 0 && (
                    <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground leading-none">
                      {count}
                    </span>
                  )}
                </button>
              );
            });
          })()}
        </div>
        <div className="p-6">
          {activeTab === 'details' && (
            <div className="space-y-6">
              {/* Metadata grid */}
              <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
                <Badge
                  label="State"
                  value={incident.state.replace('_', ' ')}
                  badgeClass={STATE_CLASSES[incident.state] ?? ''}
                  help={FIELD_HELP.State}
                />
                <InlineSelect
                  label="Severity"
                  value={incident.severity}
                  options={['critical', 'high', 'medium', 'low', 'info']}
                  colorClasses={SEVERITY_CLASSES}
                  onChange={v => handleBadgeChange('severity', v)}
                  saving={savingBadge}
                  help={FIELD_HELP.Severity}
                />
                <InlineSelect
                  label="TLP"
                  value={incident.tlp}
                  options={['white', 'green', 'amber', 'red']}
                  colorClasses={TLP_CLASSES}
                  onChange={v => handleBadgeChange('tlp', v)}
                  saving={savingBadge}
                  help={FIELD_HELP.TLP}
                />
                <InlineSelect
                  label="PAP"
                  value={incident.pap}
                  options={['white', 'green', 'amber', 'red']}
                  colorClasses={TLP_CLASSES}
                  onChange={v => handleBadgeChange('pap', v)}
                  saving={savingBadge}
                  help={FIELD_HELP.PAP}
                />
                <Field label="Organisation" value={incident.org_slug} />
                <Field label="Source"       value={incident.source_kind} help={FIELD_HELP.Source} />
                <Field label="Assignee"     value={incident.assignee_username} />
                <Field label="Created By"   value={incident.created_by_username} />
                {incident.closure_reason && (
                  <Field label="Closure Reason" value={incident.closure_reason.replace('_', ' ')} />
                )}
                {incident.duplicate_of_display_id && (
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Duplicate of</span>
                    <Link
                      to={`/incidents/${incident.duplicate_of_display_id}`}
                      className="text-sm font-mono text-primary hover:underline"
                    >
                      {incident.duplicate_of_display_id}
                    </Link>
                  </div>
                )}
                {incident.response_sla?.applies && (
                  <div className="flex flex-col gap-1">
                    <FieldLabel label="Response SLA" help={FIELD_HELP.SLA} />
                    <SLAPill sla={incident.response_sla} label="Response SLA" />
                  </div>
                )}
                {incident.resolve_sla?.applies && (
                  <div className="flex flex-col gap-1">
                    <FieldLabel label="Resolve SLA" help={FIELD_HELP.SLA} />
                    <SLAPill sla={incident.resolve_sla} label="Resolve SLA" />
                  </div>
                )}
                <SubjectDropdown
                  incident={incident}
                  subjects={subjects}
                  onSubjectChange={handleSubjectChange}
                  saving={savingSubject}
                />
              </div>

              {subjectError && <p className="text-sm text-red-600">{subjectError}</p>}

              {/* Duplicates of this incident */}
              {incident.duplicates?.length > 0 && (
                <div className="rounded-lg border border-border bg-card p-4 space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Duplicates</h3>
                  <ul className="divide-y divide-border">
                    {incident.duplicates.map(dup => (
                      <li key={dup.id} className="flex items-center gap-3 py-2">
                        <Link
                          to={`/incidents/${dup.display_id}`}
                          className="font-mono text-xs text-primary hover:underline shrink-0"
                        >
                          {dup.display_id}
                        </Link>
                        <span className="flex-1 text-sm text-foreground truncate">{dup.title}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STATE_CLASSES[dup.state] ?? ''}`}>
                          {dup.state.replace('_', ' ')}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Other incidents from the same source */}
              <LinkedIncidents
                sourceKind={incident.source_kind}
                sourceRef={incident.source_ref}
                excludeId={incident.id}
              />

              {/* Description + Activity (comments + contact messages) */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</span>
                    {incident.description ? (
                      <div className="mt-1 prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{incident.description}</ReactMarkdown>
                      </div>
                    ) : (
                      <p className="mt-1 text-sm text-muted-foreground italic">No description provided.</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
                    <span>Created: {incident.created_at ? new Date(incident.created_at).toLocaleString() : '—'}</span>
                    <span>Updated: {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : '—'}</span>
                  </div>
                </div>
                {/* Right column: comments and contact messages form the unified activity feed */}
                <div className="space-y-4">
                  <IncidentComments
                    incidentId={displayId}
                    currentUserId={user?.id}
                    isStaff={user?.is_staff ?? false}
                    refreshKey={commentsRefreshKey}
                  />
                  <ContactMessagesCard displayId={displayId} />
                </div>
              </div>

              {/* Exceptions */}
              <IncidentExceptionsSection displayId={displayId} />
            </div>
          )}
          {activeTab === 'timeline' && (
            <IncidentTimeline incidentId={displayId} refreshKey={timelineRefreshKey} />
          )}
          {activeTab === 'attachments' && (
            <IncidentAttachments incidentId={displayId} />
          )}
          {activeTab === 'tasks' && (
            <IncidentTasks
              incidentId={displayId}
              subjectId={incident.subject}
              refreshKey={tasksRefreshKey}
            />
          )}
          {activeTab === 'delegations' && (
            <DelegationPanel
              incidentId={displayId}
              activeDelegations={incident.active_delegations ?? []}
              isStaff={user?.is_staff ?? false}
              onIncidentUpdate={setIncident}
            />
          )}
          {activeTab === 'assets' && (
            <IncidentAssetsPanel
              displayId={displayId}
              isStaff={user?.is_staff ?? false}
              orgSlug={incident.org_slug}
            />
          )}
          {activeTab === 'iocs' && (
            <IOCSection iocs={incident.iocs ?? []} />
          )}
          {activeTab === 'contacts' && (
            <IncidentContactsPanel displayId={displayId} orgSlug={incident.org_slug} />
          )}
          {activeTab === 'linked_alerts' && (
            <LinkedAlertsPanel displayId={displayId} linkedAlertCount={incident.linked_alert_count ?? 0} />
          )}
        </div>
      </div>
    </div>
  );
}

const ALERT_SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const ALERT_STATE_CLASSES = {
  new:          'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  acknowledged: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  imported:     'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  ignored:      'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
};

const ALERT_SOURCE_LABELS = {
  wazuh_event:   'Wazuh',
  vulnerability: 'CVE',
  agent_finding: 'Agent',
  api:           'API',
};

function formatAlertDt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function AlertDetailModal({ alert, onClose }) {
  if (!alert) return null;
  const rows = [
    ['ID', alert.display_id],
    ['Severity', alert.severity],
    ['State', alert.state],
    ['Source', ALERT_SOURCE_LABELS[alert.source_kind] ?? alert.source_kind],
    ['Agent', alert.agent_name ?? '—'],
    ['PAP', alert.pap ?? '—'],
    ['TLP', alert.tlp ?? '—'],
    ['Acknowledged by', alert.acknowledged_by ?? '—'],
    ['Acknowledged at', formatAlertDt(alert.acknowledged_at)],
    ['Created', formatAlertDt(alert.created_at)],
    ['Updated', formatAlertDt(alert.updated_at)],
  ];
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-card p-5 shadow-xl"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Alert ${alert.display_id}`}
      >
        <div className="flex items-start justify-between gap-4">
          <h3 className="text-base font-semibold text-foreground">{alert.title}</h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-md px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            ✕
          </button>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
          {rows.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
              <dd className="truncate text-foreground" title={String(value ?? '')}>{value ?? '—'}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4">
          <p className="text-xs font-medium text-muted-foreground">Description</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{alert.description || '—'}</p>
        </div>
        <div className="mt-4">
          <p className="text-xs font-medium text-muted-foreground">Source signal (source_ref)</p>
          <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-muted/50 p-3 text-xs text-foreground">
            {JSON.stringify(alert.source_ref ?? {}, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

export function LinkedAlertsPanel({ displayId, linkedAlertCount }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(true);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');
  const [fSeverity, setFSeverity] = useState('');
  const [fState, setFState] = useState('');
  const [fSource, setFSource] = useState('');

  useEffect(() => {
    api.get(`/api/incidents/${displayId}/alerts/`)
      .then(res => { setAlerts(Array.isArray(res.data) ? res.data : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [displayId]);

  const distinct = (key) => [...new Set(alerts.map(a => a[key]).filter(Boolean))];

  const filtered = alerts.filter(a => {
    if (search) {
      const q = search.toLowerCase();
      if (!`${a.display_id} ${a.title}`.toLowerCase().includes(q)) return false;
    }
    if (fSeverity && a.severity !== fSeverity) return false;
    if (fState && a.state !== fState) return false;
    if (fSource && a.source_kind !== fSource) return false;
    return true;
  });

  const isFiltered = search || fSeverity || fState || fSource;
  const selectCls = 'rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground';

  return (
    <div className="p-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between rounded-md px-2 py-1 text-sm font-semibold text-foreground hover:bg-accent transition-colors"
      >
        <span>Linked Alerts ({linkedAlertCount})</span>
        <span className="text-muted-foreground">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="mt-3">
          {loading ? (
            <p className="text-sm text-muted-foreground px-2">Loading…</p>
          ) : alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground px-2">No linked alerts.</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <input
                  type="search"
                  placeholder="Search alerts…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="min-w-[10rem] flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
                />
                <select value={fSeverity} onChange={e => setFSeverity(e.target.value)} className={selectCls} aria-label="Filter by severity">
                  <option value="">All severities</option>
                  {distinct('severity').map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <select value={fState} onChange={e => setFState(e.target.value)} className={selectCls} aria-label="Filter by state">
                  <option value="">All states</option>
                  {distinct('state').map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <select value={fSource} onChange={e => setFSource(e.target.value)} className={selectCls} aria-label="Filter by source">
                  <option value="">All sources</option>
                  {distinct('source_kind').map(v => <option key={v} value={v}>{ALERT_SOURCE_LABELS[v] ?? v}</option>)}
                </select>
                {isFiltered && (
                  <span className="text-xs text-muted-foreground">
                    Showing {filtered.length} of {alerts.length}
                  </span>
                )}
              </div>

              {filtered.length === 0 ? (
                <p className="text-sm text-muted-foreground px-2">No alerts match the current filters.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">ID</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">Title</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">Severity</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">Source</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">Agent</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">State</th>
                        <th className="px-2 py-1.5 text-left text-xs font-semibold text-muted-foreground">Created</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filtered.map(a => (
                        <tr
                          key={a.display_id}
                          onClick={() => setSelected(a)}
                          className="cursor-pointer hover:bg-muted/30"
                        >
                          <td className="px-2 py-2 font-mono text-xs font-medium">{a.display_id}</td>
                          <td className="px-2 py-2 text-foreground max-w-xs truncate">{a.title}</td>
                          <td className="px-2 py-2">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ALERT_SEVERITY_CLASSES[a.severity] ?? ''}`}>
                              {a.severity}
                            </span>
                          </td>
                          <td className="px-2 py-2">
                            <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-700 dark:text-slate-300">
                              {ALERT_SOURCE_LABELS[a.source_kind] ?? a.source_kind}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-xs text-muted-foreground font-mono">{a.agent_name ?? '—'}</td>
                          <td className="px-2 py-2">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ALERT_STATE_CLASSES[a.state] ?? ''}`}>
                              {a.state}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-xs text-muted-foreground whitespace-nowrap">{formatAlertDt(a.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}

      <AlertDetailModal alert={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
