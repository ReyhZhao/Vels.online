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
import CreateExceptionSlideOver from '../components/CreateExceptionSlideOver';
import ContactMessagesCard from '../components/ContactMessagesCard';
import ContactComposeModal from '../components/ContactComposeModal';

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
  resolved:     'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  closed:       'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

// States from which the resolve dropdown (Resolved / Needs tuning) is shown.
const RESOLVE_DROPDOWN_STATES = new Set(['in_progress', 'on_hold']);

const ALLOWED_TRANSITIONS = {
  new:          [{ state: 'triaged', label: 'Triage' }, { state: 'in_progress', label: 'Start work' }],
  triaged:      [{ state: 'in_progress', label: 'Start work' }, { state: 'on_hold', label: 'Put on hold' }],
  in_progress:  [{ state: 'on_hold', label: 'Put on hold' }, { state: 'closed', label: 'Close' }],
  on_hold:      [{ state: 'in_progress', label: 'Resume' }, { state: 'closed', label: 'Close' }],
  needs_tuning: [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  resolved:     [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  closed:       [{ state: 'in_progress', label: 'Reopen' }],
};

const TRANSITION_BTN_CLASSES = {
  triaged:      'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  in_progress:  'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  on_hold:      'bg-amber-500 text-white hover:bg-amber-600 dark:bg-amber-600 dark:hover:bg-amber-500',
  needs_tuning: 'bg-amber-600 text-white hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600',
  resolved:     'bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600',
  closed:       'bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600',
};

const CLOSURE_REASONS = [
  { value: 'resolved',       label: 'Resolved' },
  { value: 'false_positive', label: 'False Positive' },
  { value: 'duplicate',      label: 'Duplicate' },
  { value: 'informational',  label: 'Informational' },
  { value: 'accepted_risk',  label: 'Accepted Risk' },
];

const TABS = [
  { key: 'details',     label: 'Details' },
  { key: 'timeline',    label: 'Timeline' },
  { key: 'attachments', label: 'Attachments' },
  { key: 'tasks',       label: 'Tasks' },
  { key: 'delegations', label: 'Delegations' },
  { key: 'assets',      label: 'Assets' },
  { key: 'iocs',        label: 'IOCs' },
  { key: 'contacts',    label: 'Contacts' },
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

const IOC_KIND_LABELS = { ip: 'IP Address', domain: 'Domain', url: 'URL' };
const IOC_KIND_CLASSES = {
  ip:     'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  domain: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  url:    'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

function IOCSection({ iocs }) {
  const grouped = iocs.reduce((acc, ioc) => {
    if (!acc[ioc.kind]) acc[ioc.kind] = [];
    acc[ioc.kind].push(ioc);
    return acc;
  }, {});

  const kinds = ['ip', 'domain', 'url'].filter(k => grouped[k]?.length);

  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-4">
      <h2 className="text-base font-semibold text-foreground">Indicators of Compromise</h2>
      {kinds.length === 0 ? (
        <p className="text-sm text-muted-foreground">No IOCs were extracted from this incident.</p>
      ) : (
        <div className="space-y-3">
          {kinds.map(kind => (
            <div key={kind}>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                {IOC_KIND_LABELS[kind]}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {grouped[kind].map(ioc => (
                  <span
                    key={ioc.id}
                    className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-mono ${IOC_KIND_CLASSES[kind]}`}
                  >
                    {ioc.value}
                  </span>
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

function Badge({ label, value, badgeClass }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
        {value}
      </span>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-sm text-foreground">{value || '—'}</span>
    </div>
  );
}

function InlineSelect({ label, value, options, colorClasses, onChange, saving }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
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

function ClosureReasonDialog({ onConfirm, onCancel, transitioning }) {
  const [reason, setReason] = useState('');
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
            onChange={e => setReason(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a reason…</option>
            {CLOSURE_REASONS.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={transitioning}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => reason && onConfirm(reason)}
            disabled={!reason || transitioning}
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
  const [showTransferDialog, setShowTransferDialog] = useState(false);
  const [staffUsers, setStaffUsers]       = useState([]);
  const [transferring, setTransferring]   = useState(false);
  const [transferError, setTransferError] = useState(null);
  const [savingBadge, setSavingBadge]     = useState(false);
  const [badgeError, setBadgeError]       = useState(null);
  const [activeTab, setActiveTab]         = useState('details');
  const [showExceptionSlideOver, setShowExceptionSlideOver] = useState(false);
  const [triaging, setTriaging]           = useState(false);
  const [triageQueued, setTriageQueued]   = useState(false);
  const [triageError, setTriageError]     = useState(null);
  const pollRef = useRef(null);

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

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        api.get(`/api/incidents/${displayId}/`)
          .then(res => setIncident(prev => prev ? res.data : prev))
          .catch(() => {});
      }
    }, 30000);
    return () => clearInterval(pollRef.current);
  }, [displayId]);

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

  async function handleTransition(targetState, closureReason = undefined) {
    setTransitioning(true);
    setTransitionError(null);
    try {
      const payload = { state: targetState };
      if (closureReason) payload.closure_reason = closureReason;
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

  function handleActionClick(targetState) {
    if (targetState === 'closed') {
      setPendingClose(true);
    } else {
      handleTransition(targetState);
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
          onConfirm={reason => handleTransition('closed', reason)}
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

      <CreateExceptionSlideOver
        open={showExceptionSlideOver}
        onClose={() => setShowExceptionSlideOver(false)}
        incident={incident}
      />

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
                onResolve={() => handleActionClick('resolved')}
                onNeedsTuning={() => handleActionClick('needs_tuning')}
                disabled={transitioning}
              />
            )}
            {user?.is_staff && (
              <button
                onClick={handleOpenTransfer}
                disabled={transitioning || transferring}
                className="rounded-md border border-slate-400 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {incident.assignee_username ? 'Transfer' : 'Assign'}
              </button>
            )}
            {user?.is_staff && incident.source_kind === 'wazuh_event' && (
              <button
                onClick={() => setShowExceptionSlideOver(true)}
                className="rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors dark:border-amber-600 dark:bg-amber-900/20 dark:text-amber-400 dark:hover:bg-amber-900/40"
              >
                Create Exception
              </button>
            )}
            {user?.is_staff && incident.state !== 'closed' && (
              <button
                onClick={handleTriage}
                disabled={triaging || triageQueued || transitioning}
                className="rounded-md border border-violet-400 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:border-violet-600 dark:bg-violet-900/20 dark:text-violet-400 dark:hover:bg-violet-900/40"
              >
                {triaging ? 'Triaging…' : triageQueued ? 'Triage queued' : 'Run Triage'}
              </button>
            )}
          </div>
        </div>
        {transitionError && <p className="text-sm text-red-600">{transitionError}</p>}
        {transferError   && <p className="text-sm text-red-600">{transferError}</p>}
        {badgeError      && <p className="text-sm text-red-600">{badgeError}</p>}
        {triageError     && <p className="text-sm text-red-600">{triageError}</p>}
      </div>

      {/* ── Tabbed content ── */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="flex overflow-x-auto border-b border-border scrollbar-none">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`shrink-0 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
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
                />
                <InlineSelect
                  label="Severity"
                  value={incident.severity}
                  options={['critical', 'high', 'medium', 'low', 'info']}
                  colorClasses={SEVERITY_CLASSES}
                  onChange={v => handleBadgeChange('severity', v)}
                  saving={savingBadge}
                />
                <InlineSelect
                  label="TLP"
                  value={incident.tlp}
                  options={['white', 'green', 'amber', 'red']}
                  colorClasses={TLP_CLASSES}
                  onChange={v => handleBadgeChange('tlp', v)}
                  saving={savingBadge}
                />
                <InlineSelect
                  label="PAP"
                  value={incident.pap}
                  options={['white', 'green', 'amber', 'red']}
                  colorClasses={TLP_CLASSES}
                  onChange={v => handleBadgeChange('pap', v)}
                  saving={savingBadge}
                />
                <Field label="Organisation" value={incident.org_slug} />
                <Field label="Source"       value={incident.source_kind} />
                <Field label="Assignee"     value={incident.assignee_username} />
                <Field label="Created By"   value={incident.created_by_username} />
                {incident.closure_reason && (
                  <Field label="Closure Reason" value={incident.closure_reason.replace('_', ' ')} />
                )}
                {incident.response_sla?.applies && (
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Response SLA</span>
                    <SLAPill sla={incident.response_sla} label="Response SLA" />
                  </div>
                )}
                {incident.resolve_sla?.applies && (
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Resolve SLA</span>
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

              {/* Description + Comments */}
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
                <div>
                  <IncidentComments
                    incidentId={displayId}
                    currentUserId={user?.id}
                    isStaff={user?.is_staff ?? false}
                  />
                </div>
              </div>

              {/* Exceptions */}
              <IncidentExceptionsSection displayId={displayId} />

              {/* Contact Messages */}
              <ContactMessagesCard displayId={displayId} />
            </div>
          )}
          {activeTab === 'timeline' && (
            <IncidentTimeline incidentId={displayId} />
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
        </div>
      </div>
    </div>
  );
}
