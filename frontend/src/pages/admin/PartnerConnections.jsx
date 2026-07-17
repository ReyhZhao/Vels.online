import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '@/lib/axios';

const MAPPED_FIELDS = ['severity', 'tlp', 'pap', 'title', 'description'];

const KIND_LABELS = { csirt_peer: 'CSIRT / Peer', vendor: 'Vendor' };
const DIRECTION_LABELS = { inbound_only: 'Inbound only', bidirectional: 'Bidirectional' };

// value_map is edited as `KEY=value, KEY2=value2` for friendliness; stored as an object.
function parseValueMap(text) {
  const out = {};
  (text || '').split(',').forEach(pair => {
    const [k, ...rest] = pair.split('=');
    const key = (k || '').trim();
    const val = rest.join('=').trim();
    if (key && val) out[key] = val;
  });
  return out;
}
function formatValueMap(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join(', ');
}

function emptyMappingForm() {
  const m = {};
  MAPPED_FIELDS.forEach(f => { m[f] = { regex: '', value_map: '', default: '' }; });
  return m;
}

function mappingFormFromApi(field_mappings) {
  const m = emptyMappingForm();
  Object.entries(field_mappings || {}).forEach(([f, cfg]) => {
    if (!m[f]) return;
    m[f] = {
      regex: cfg.regex || '',
      value_map: formatValueMap(cfg.value_map),
      default: cfg.default || '',
    };
  });
  return m;
}

function mappingFormToApi(form) {
  const out = {};
  MAPPED_FIELDS.forEach(f => {
    const cfg = form[f] || {};
    const regex = (cfg.regex || '').trim();
    const value_map = parseValueMap(cfg.value_map);
    const dflt = (cfg.default || '').trim();
    if (regex || Object.keys(value_map).length || dflt) {
      out[f] = { regex, value_map, default: dflt };
    }
  });
  return out;
}

function ConnectionForm({ initial, defaultSenders, orgs, onSaved, onCancel }) {
  const infraOrg = orgs.find(o => o.is_infrastructure);
  const firstTenant = orgs.find(o => !o.is_infrastructure);
  const [name, setName] = useState(initial?.name ?? '');
  const [kind, setKind] = useState(initial?.kind ?? 'csirt_peer');
  const [orgId, setOrgId] = useState(
    initial?.organization ?? (firstTenant?.id ?? orgs[0]?.id ?? '')
  );
  const [direction, setDirection] = useState(initial?.direction ?? 'bidirectional');
  const [refRegex, setRefRegex] = useState(initial?.external_reference_regex ?? '');
  const [senders, setSenders] = useState((initial?.sender_addresses ?? defaultSenders ?? []).join('\n'));
  const [active, setActive] = useState(initial?.active ?? true);
  const [mapping, setMapping] = useState(mappingFormFromApi(initial?.field_mappings));
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  // Kind drives the default target org + direction (AC #669). Only re-default when the
  // user picks a kind, not on an existing record load.
  function handleKindChange(next) {
    setKind(next);
    if (next === 'vendor') {
      if (infraOrg) setOrgId(infraOrg.id);
      setDirection('inbound_only');
    } else {
      setDirection('bidirectional');
    }
  }

  function setMap(field, key, value) {
    setMapping(prev => ({ ...prev, [field]: { ...prev[field], [key]: value } }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const addresses = senders.split(/[\n,]/).map(s => s.trim()).filter(Boolean);
    const errs = {};
    if (!name.trim()) errs.name = 'Required.';
    if (!orgId) errs.organization = 'Required.';
    if (addresses.length === 0) errs.sender_addresses = 'At least one sender address.';
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setSaving(true);
    setErrors({});
    const payload = {
      name: name.trim(),
      kind,
      organization: orgId,
      direction,
      external_reference_regex: refRegex.trim(),
      field_mappings: mappingFormToApi(mapping),
      sender_addresses: addresses,
      active,
    };
    try {
      const res = initial
        ? await api.patch(`/api/partners/connections/${initial.id}/`, payload)
        : await api.post('/api/partners/connections/', payload);
      onSaved(res.data, !initial);
    } catch (err) {
      const data = err.response?.data;
      if (data && typeof data === 'object') {
        const flat = {};
        Object.entries(data).forEach(([k, v]) => { flat[k] = Array.isArray(v) ? v.join(' ') : String(v); });
        setErrors(flat);
      } else {
        setErrors({ _: 'Failed to save Connection.' });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-background p-6 shadow-xl">
        <h2 className="mb-4 text-base font-semibold text-foreground">
          {initial ? 'Edit Connection' : 'New Connection'}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
              <input value={name} onChange={e => setName(e.target.value)} disabled={saving}
                aria-label="Connection name"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm" />
              {errors.name && <p className="mt-0.5 text-xs text-red-600">{errors.name}</p>}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Kind</label>
              <select value={kind} onChange={e => handleKindChange(e.target.value)} disabled={saving}
                aria-label="Connection kind"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm">
                <option value="csirt_peer">CSIRT / Peer</option>
                <option value="vendor">Vendor</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Target organization</label>
              <select value={orgId} onChange={e => setOrgId(Number(e.target.value))} disabled={saving}
                aria-label="Target organization"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm">
                <option value="">Select…</option>
                {orgs.map(o => (
                  <option key={o.id} value={o.id}>{o.name}{o.is_infrastructure ? ' (Infrastructure)' : ''}</option>
                ))}
              </select>
              {errors.organization && <p className="mt-0.5 text-xs text-red-600">{errors.organization}</p>}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Direction</label>
              <select value={direction} onChange={e => setDirection(e.target.value)} disabled={saving}
                aria-label="Connection direction"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm">
                <option value="inbound_only">Inbound only</option>
                <option value="bidirectional">Bidirectional</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Sender addresses <span className="font-normal">(one per line — unique across all Connections)</span>
            </label>
            <textarea value={senders} onChange={e => setSenders(e.target.value)} disabled={saving} rows={2}
              aria-label="Sender addresses"
              placeholder="soc@peer.example"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono" />
            {errors.sender_addresses && <p className="mt-0.5 text-xs text-red-600">{errors.sender_addresses}</p>}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              External Reference regex <span className="font-normal">(over the subject; leave empty to disable)</span>
            </label>
            <input value={refRegex} onChange={e => setRefRegex(e.target.value)} disabled={saving}
              aria-label="External reference regex"
              placeholder="\[(INC-\d+)\]"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono" />
            {errors.external_reference_regex && <p className="mt-0.5 text-xs text-red-600">{errors.external_reference_regex}</p>}
          </div>

          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Field mapping <span className="font-normal">(regex over subject/body → value map → default). Empty regex uses the default.</span>
            </p>
            <div className="space-y-2 rounded-md border border-border p-2">
              {MAPPED_FIELDS.map(f => (
                <div key={f} className="grid grid-cols-1 gap-2 sm:grid-cols-[5rem_1fr_1fr_1fr] sm:items-center">
                  <span className="text-xs font-medium text-foreground">{f}</span>
                  <input value={mapping[f].regex} onChange={e => setMap(f, 'regex', e.target.value)} disabled={saving}
                    aria-label={`${f} regex`} placeholder="regex"
                    className="rounded border border-border bg-background px-2 py-1 text-xs font-mono" />
                  <input value={mapping[f].value_map} onChange={e => setMap(f, 'value_map', e.target.value)} disabled={saving}
                    aria-label={`${f} value map`} placeholder="P1=critical, P2=high"
                    className="rounded border border-border bg-background px-2 py-1 text-xs font-mono" />
                  <input value={mapping[f].default} onChange={e => setMap(f, 'default', e.target.value)} disabled={saving}
                    aria-label={`${f} default`} placeholder="default"
                    className="rounded border border-border bg-background px-2 py-1 text-xs" />
                </div>
              ))}
            </div>
            {errors.field_mappings && <p className="mt-0.5 text-xs text-red-600">{errors.field_mappings}</p>}
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} disabled={saving}
              className="rounded border-border" />
            Active
          </label>

          {errors._ && <p className="text-xs text-red-600">{errors._}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onCancel} disabled={saving} className="text-sm text-muted-foreground hover:underline">Cancel</button>
            <button type="submit" disabled={saving} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {saving ? 'Saving…' : (initial ? 'Save' : 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const SORT_COLUMNS = { name: 'Name', kind: 'Kind', organization_name: 'Organization' };

export default function PartnerConnections() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [connections, setConnections] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [editing, setEditing] = useState(null); // connection | 'new' | null
  const [prefillSender, setPrefillSender] = useState('');
  const [replayOffer, setReplayOffer] = useState(null); // { connection, preview } | null
  const [replaying, setReplaying] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get('/api/partners/connections/'),
      api.get('/api/security/organizations/', { params: { include_infrastructure: '1' } }),
    ])
      .then(([c, o]) => { setConnections(c.data); setOrgs(o.data); })
      .catch(() => setError('Failed to load Connections.'))
      .finally(() => setLoading(false));
  }, []);

  // Deep-link from the Intake Inbox (slice 7): ?sender=<addr> opens the create form
  // with the sender pre-filled.
  useEffect(() => {
    const sender = searchParams.get('sender');
    if (sender) {
      setPrefillSender(sender);
      setEditing('new');
      searchParams.delete('sender');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  function setSort(key) {
    if (sortKey === key) setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortOrder('asc'); }
  }

  async function handleSaved(saved, isNew) {
    setConnections(prev => isNew ? [...prev, saved] : prev.map(c => c.id === saved.id ? saved : c));
    setEditing(null);
    setPrefillSender('');
    // Offer to replay any held Intake Inbox backlog these senders now cover (ADR-0035).
    // Best-effort: a preview failure must not break the save.
    try {
      const { data } = await api.get(`/api/partners/connections/${saved.id}/replay-intake/`);
      if (data.count > 0) setReplayOffer({ connection: saved, preview: data });
    } catch { /* ignore — replay stays available later from the Intake Inbox */ }
  }

  async function confirmReplay() {
    setReplaying(true);
    try {
      await api.post(`/api/partners/connections/${replayOffer.connection.id}/replay-intake/`);
      setReplayOffer(null);
    } catch {
      setError('Failed to replay held messages.');
    } finally {
      setReplaying(false);
    }
  }

  async function handleDelete(conn) {
    if (!window.confirm(`Delete Connection "${conn.name}"?`)) return;
    try {
      await api.delete(`/api/partners/connections/${conn.id}/`);
      setConnections(prev => prev.filter(c => c.id !== conn.id));
    } catch {
      setError('Failed to delete Connection.');
    }
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = connections.filter(c => {
      if (kindFilter !== 'all' && c.kind !== kindFilter) return false;
      if (statusFilter === 'active' && !c.active) return false;
      if (statusFilter === 'inactive' && c.active) return false;
      if (!q) return true;
      return (
        (c.name || '').toLowerCase().includes(q) ||
        (c.organization_name || '').toLowerCase().includes(q) ||
        (c.sender_addresses || []).some(a => a.toLowerCase().includes(q))
      );
    });
    const dir = sortOrder === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) =>
      (a[sortKey] || '').toString().toLowerCase().localeCompare((b[sortKey] || '').toString().toLowerCase()) * dir,
    );
    return rows;
  }, [connections, search, kindFilter, statusFilter, sortKey, sortOrder]);

  function SortHeader({ field }) {
    return (
      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <button onClick={() => setSort(field)} aria-label={`Sort by ${SORT_COLUMNS[field]}`}
          className="flex items-center gap-1 uppercase hover:text-foreground transition-colors">
          {SORT_COLUMNS[field]}
          {sortKey === field && <span aria-hidden="true">{sortOrder === 'asc' ? '▲' : '▼'}</span>}
        </button>
      </th>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Partner Connections</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Email channels through which peer CSIRTs and vendors feed incidents into the platform.
          </p>
        </div>
        <button onClick={() => { setPrefillSender(''); setEditing('new'); }}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground">
          New Connection
        </button>
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input type="search" placeholder="Search connections…" value={search}
          onChange={e => setSearch(e.target.value)} aria-label="Search connections"
          className="w-52 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring" />
        <select value={kindFilter} onChange={e => setKindFilter(e.target.value)} aria-label="Kind filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground">
          <option value="all">All kinds</option>
          <option value="csirt_peer">CSIRT / Peer</option>
          <option value="vendor">Vendor</option>
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} aria-label="Status filter"
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground">
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No Connections configured.</p>
        ) : visible.map(c => (
          <div key={c.id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-1">
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium text-foreground">{c.name}</p>
              {c.active
                ? <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-xs text-green-800 dark:bg-green-900/30 dark:text-green-400">Active</span>
                : <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">Inactive</span>}
            </div>
            <p className="text-xs text-muted-foreground">{KIND_LABELS[c.kind]} · {DIRECTION_LABELS[c.direction]} · {c.organization_name}</p>
            <p className="font-mono text-xs text-muted-foreground">{(c.sender_addresses || []).join(', ')}</p>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setEditing(c)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
              <button onClick={() => handleDelete(c)} className="text-xs text-red-600 hover:underline">Delete</button>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block rounded-lg border border-border bg-card">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border">
              <SortHeader field="name" />
              <SortHeader field="kind" />
              <SortHeader field="organization_name" />
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Direction</th>
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Senders</th>
              <th className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">No Connections configured.</td></tr>
            ) : visible.map(c => (
              <tr key={c.id} className="border-b border-border last:border-0 hover:bg-accent/20">
                <td className="px-4 py-3 text-sm font-medium text-foreground">{c.name}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground">{KIND_LABELS[c.kind]}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground">{c.organization_name}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground">{DIRECTION_LABELS[c.direction]}</td>
                <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{(c.sender_addresses || []).join(', ')}</td>
                <td className="px-4 py-3 text-xs">
                  {c.active
                    ? <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-green-800 dark:bg-green-900/30 dark:text-green-400">Active</span>
                    : <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-700 dark:text-gray-400">Inactive</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button onClick={() => setEditing(c)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">Edit</button>
                    <button onClick={() => handleDelete(c)} className="text-xs text-red-600 hover:underline">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <ConnectionForm
          initial={editing === 'new' ? null : editing}
          defaultSenders={editing === 'new' && prefillSender ? [prefillSender] : []}
          orgs={orgs}
          onSaved={handleSaved}
          onCancel={() => { setEditing(null); setPrefillSender(''); }}
        />
      )}

      {replayOffer && (
        <ReplayOffer
          offer={replayOffer}
          replaying={replaying}
          onReplay={confirmReplay}
          onDismiss={() => setReplayOffer(null)}
        />
      )}
    </div>
  );
}

function ReplayOffer({ offer, replaying, onReplay, onDismiss }) {
  const { connection, preview } = offer;
  const fragmenting = preview.without_reference > 0;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-background p-6 shadow-xl">
        <h2 className="mb-2 text-base font-semibold text-foreground">Replay held messages?</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          {preview.count} held message{preview.count === 1 ? '' : 's'} from{' '}
          <span className="font-medium text-foreground">{connection.name}</span>’s senders can be
          replayed into incidents now. Declining leaves them held — you can replay them later from
          the Intake Inbox.
        </p>

        {fragmenting && (
          <p className="mb-3 rounded-md bg-amber-100 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
            {preview.without_reference} message{preview.without_reference === 1 ? '' : 's'} have no
            extracted reference and will each open a <strong>separate flagged incident</strong>
            {' '}rather than threading together. Add an External Reference regex first if these
            should be one incident.
          </p>
        )}

        <ul className="mb-4 max-h-60 space-y-1 overflow-y-auto rounded-md border border-border p-2 text-xs">
          {preview.messages.map(m => (
            <li key={m.id} className="flex items-center justify-between gap-2">
              <span className="truncate text-muted-foreground" title={m.subject}>{m.subject || '(no subject)'}</span>
              {m.has_reference
                ? <span className="whitespace-nowrap font-mono text-foreground">→ {m.external_reference}</span>
                : <span className="whitespace-nowrap text-amber-600 dark:text-amber-400">no reference</span>}
            </li>
          ))}
        </ul>

        <div className="flex justify-end gap-3">
          <button type="button" onClick={onDismiss} disabled={replaying}
            className="text-sm text-muted-foreground hover:underline">Not now</button>
          <button type="button" onClick={onReplay} disabled={replaying}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
            {replaying ? 'Replaying…' : 'Replay now'}
          </button>
        </div>
      </div>
    </div>
  );
}
