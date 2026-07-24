import { useEffect, useMemo, useState } from 'react';
import api from '@/lib/axios';
import {
  ECS_TARGETS, TARGET_FIELDS, elementsFor, formatValueMap, getByPath,
  mappingsToApi, parseValueMap, resolveField,
} from './ingest/mappingEngine';
import { JsonTree, RecordPreview, StatusBadge } from './ingest/InspectorWidgets';

const TARGET_LABELS = { incident: 'Incident', alert: 'Alert', asset: 'Asset' };
const STATUSES = ['pending', 'created', 'failed', 'partial'];
const INPUT = 'rounded border border-input bg-background px-2 py-1 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring';

function mappingsFromApi(keys, apiMap) {
  const m = {};
  keys.forEach(k => {
    const cfg = (apiMap || {})[k] || {};
    m[k] = {
      kind: cfg.kind || 'path',
      path: cfg.path || '',
      value: cfg.value || '',
      value_map: cfg.value_map || {},
      default: cfg.default || '',
    };
  });
  return m;
}

// ── Create ─────────────────────────────────────────────────────────────────────────────

function CreateForm({ orgs, onSaved, onCancel }) {
  const [name, setName] = useState('');
  const [targetType, setTargetType] = useState('incident');
  const [orgId, setOrgId] = useState(orgs[0]?.id ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function submit(e) {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const { data } = await api.post('/api/ingest-endpoints/endpoints/', {
        name, target_type: targetType, organization: orgId,
      });
      onSaved(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not create endpoint.');
    } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="mb-4 space-y-3 rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold text-foreground">New Ingest Endpoint</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Name
          <input aria-label="Endpoint name" value={name} onChange={e => setName(e.target.value)} required className={INPUT} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Target type
          <select aria-label="Target type" value={targetType} onChange={e => setTargetType(e.target.value)} className={INPUT}>
            {Object.entries(TARGET_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Organization
          <select aria-label="Target organization" value={orgId} onChange={e => setOrgId(e.target.value)} className={INPUT}>
            {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </label>
      </div>
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50">Create</button>
        <button type="button" onClick={onCancel} className="rounded-md border border-border px-3 py-1 text-xs text-muted-foreground">Cancel</button>
      </div>
    </form>
  );
}

// ── Inspector mapping builder ────────────────────────────────────────────────────────────

function MappingBuilder({ endpoint, onUpdated }) {
  const isAlert = endpoint.target_type === 'alert';
  const fields = TARGET_FIELDS[endpoint.target_type] || [];
  const [collectionRoot, setCollectionRoot] = useState(endpoint.collection_root_path || '');
  const [idemPath, setIdemPath] = useState(endpoint.idempotency_key_path || '');
  const [mappings, setMappings] = useState(() => mappingsFromApi(fields.map(f => f.key), endpoint.field_mappings));
  const [ecs, setEcs] = useState(() => mappingsFromApi(ECS_TARGETS, endpoint.entity_mappings));
  const [picked, setPicked] = useState(null);
  const [samples, setSamples] = useState([]);
  const [sampleId, setSampleId] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    api.get(`/api/ingest-endpoints/endpoints/${endpoint.id}/captured/`)
      .then(({ data }) => {
        const rows = data.results || data;
        setSamples(rows);
        if (rows.length) setSampleId(String(rows[0].id));
      })
      .catch(() => setSamples([]));
  }, [endpoint.id]);

  const sample = samples.find(s => String(s.id) === String(sampleId));
  const body = sample?.body ?? null;
  const firstEl = elementsFor(body, collectionRoot)[0] || {};

  function assign(fieldKey, isEcs) {
    if (!picked) return;
    const setter = isEcs ? setEcs : setMappings;
    setter(prev => ({ ...prev, [fieldKey]: { ...(prev[fieldKey] || {}), kind: 'path', path: picked } }));
  }
  function clearField(fieldKey, isEcs) {
    const setter = isEcs ? setEcs : setMappings;
    setter(prev => ({ ...prev, [fieldKey]: { ...(prev[fieldKey] || {}), path: '' } }));
  }
  function setValueMap(fieldKey, text) {
    setMappings(prev => ({ ...prev, [fieldKey]: { ...prev[fieldKey], value_map: parseValueMap(text) } }));
  }

  async function save() {
    setMsg('');
    try {
      const { data } = await api.patch(`/api/ingest-endpoints/endpoints/${endpoint.id}/`, {
        collection_root_path: collectionRoot,
        idempotency_key_path: idemPath,
        field_mappings: mappingsToApi(mappings),
        entity_mappings: isAlert ? mappingsToApi(ecs) : {},
      });
      onUpdated(data);
      setMsg('Mapping saved.');
    } catch { setMsg('Could not save mapping.'); }
  }

  return (
    <section aria-label="Mapping builder" className="mt-5">
      <p className="mb-3 text-sm text-muted-foreground">
        Click a value on the left to select it, then <b className="text-foreground">Assign</b> it to a target field.
        Paths are relative to each <code className="text-foreground">Collection Root</code> element.
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1 text-xs text-muted-foreground">Collection Root
          <input aria-label="Collection root path" value={collectionRoot} onChange={e => setCollectionRoot(e.target.value)} placeholder="results" className={`w-28 font-mono text-xs ${INPUT}`} />
        </label>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">Idempotency key
          <input aria-label="Idempotency key path" value={idemPath} onChange={e => setIdemPath(e.target.value)} placeholder="event_id" className={`w-32 font-mono text-xs ${INPUT}`} />
        </label>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">Map against
          <select aria-label="Preview sample" value={sampleId} onChange={e => setSampleId(e.target.value)} className={INPUT}>
            <option value="">— sample —</option>
            {samples.map(s => <option key={s.id} value={s.id}>#{s.id} · {s.status}</option>)}
          </select>
        </label>
      </div>

      {samples.length === 0 && (
        <p className="rounded-md border border-dashed border-border bg-background p-3 text-xs text-muted-foreground">
          No captured payloads yet — POST a sample to this endpoint&apos;s URL, then map against it here.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* LEFT — raw payload, click to pick */}
        <section className="rounded-lg border border-border bg-card p-3">
          <h4 className="mb-2 text-sm font-semibold text-foreground">Captured payload</h4>
          {picked && (
            <div className="mb-2 flex items-center justify-between rounded bg-primary/15 px-2 py-1 font-mono text-xs">
              <span className="truncate text-primary">
                picked: {picked} <span className="text-muted-foreground">= {JSON.stringify(getByPath(firstEl, picked))}</span>
              </span>
              <button type="button" onClick={() => setPicked(null)} className="ml-2 shrink-0 text-muted-foreground hover:text-foreground" aria-label="Clear selection">✕</button>
            </div>
          )}
          <div className="max-h-[26rem] overflow-auto rounded bg-background p-2">
            <div className="mb-1 font-mono text-[11px] text-muted-foreground">
              {collectionRoot ? `${collectionRoot}[0] (element view)` : 'body'}
            </div>
            <JsonTree data={firstEl} onPick={setPicked} activePath={picked} />
          </div>
        </section>

        {/* RIGHT — target fields */}
        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-foreground">Target: {TARGET_LABELS[endpoint.target_type]} fields</h4>
          {fields.map(f => {
            const m = mappings[f.key];
            const r = resolveField(m, firstEl);
            return (
              <div key={f.key} className="rounded-lg border border-border bg-card p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{f.label}{f.required && <span className="text-red-400">*</span>}</span>
                  <button type="button" aria-label={`Assign to ${f.key}`} disabled={!picked} onClick={() => assign(f.key)}
                    className="rounded bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground disabled:opacity-40">
                    Assign ‹{picked || '…'}›
                  </button>
                </div>
                <div className="mt-1 flex items-center justify-between gap-2 font-mono text-xs">
                  {m?.path ? <span className="text-muted-foreground">← {m.path}</span> : <span className="text-red-400">unmapped</span>}
                  {m?.path && <button type="button" onClick={() => clearField(f.key)} className="text-muted-foreground hover:text-foreground">clear</button>}
                </div>
                {f.enum && (
                  <input aria-label={`${f.key} value map`} defaultValue={formatValueMap(m?.value_map)} onBlur={e => setValueMap(f.key, e.target.value)}
                    className={`mt-1.5 w-full font-mono text-[11px] ${INPUT}`} placeholder="value map: warning=medium, crit=critical" />
                )}
                <div className="mt-1.5 flex items-center gap-1.5 text-xs">
                  <span className="text-muted-foreground">→</span>
                  {r.ok
                    ? <span className="rounded bg-emerald-400/15 px-1.5 py-0.5 text-emerald-300">{String(r.value)}</span>
                    : <span className="text-red-400">unresolved</span>}
                </div>
              </div>
            );
          })}

          {isAlert && (
            <>
              <h4 className="pt-1 text-sm font-semibold text-foreground">ECS entities <span className="font-normal text-muted-foreground">(≥1 required)</span></h4>
              <div className="rounded-lg border border-border bg-card p-2.5">
                {ECS_TARGETS.map(key => {
                  const r = resolveField(ecs[key], firstEl);
                  return (
                    <div key={key} className="flex items-center justify-between gap-2 border-b border-border py-1 last:border-0">
                      <span className="font-mono text-xs text-foreground">{key}</span>
                      <div className="flex items-center gap-2">
                        {r.ok
                          ? <span className="rounded bg-indigo-400/20 px-1.5 py-0.5 font-mono text-[10px] text-indigo-200">{String(r.value)}</span>
                          : <span className="font-mono text-[11px] text-muted-foreground">—</span>}
                        <button type="button" aria-label={`Assign to ${key}`} disabled={!picked} onClick={() => assign(key, true)}
                          className="rounded border border-input px-1.5 py-0.5 text-[11px] text-foreground hover:bg-accent disabled:opacity-40">Assign</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>
      </div>

      <section className="mt-4">
        <h4 className="mb-2 text-sm font-semibold text-foreground">Dry-run preview {sample && <span className="font-normal text-muted-foreground">— #{sample.id}</span>}</h4>
        {body != null
          ? <RecordPreview body={body} collectionRoot={collectionRoot} targetType={endpoint.target_type} fields={fields} mappings={mappings} ecs={ecs} />
          : <p className="text-xs text-muted-foreground">Pick a captured payload to preview.</p>}
      </section>

      <div className="mt-3 flex items-center gap-3">
        <button type="button" onClick={save} className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">Save mapping</button>
        {msg && <span role="status" className="text-xs text-muted-foreground">{msg}</span>}
      </div>
    </section>
  );
}

// ── Captured payloads / dead-letter ──────────────────────────────────────────────────────

function CapturedPanel({ endpoint }) {
  const [statusFilter, setStatusFilter] = useState('');
  const [rows, setRows] = useState([]);

  useEffect(() => {
    const q = statusFilter ? `?status=${statusFilter}` : '';
    api.get(`/api/ingest-endpoints/endpoints/${endpoint.id}/captured/${q}`)
      .then(({ data }) => setRows(data.results || data))
      .catch(() => setRows([]));
  }, [endpoint.id, statusFilter]);

  return (
    <section aria-label="Captured payloads" className="mt-8 rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <h3 className="text-sm font-semibold text-foreground">Captured payloads <span className="font-normal text-muted-foreground">· dead-letter</span></h3>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">Status
          <select aria-label="Status filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={INPUT}>
            <option value="">All</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr><th className="px-4 py-2">#</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Received</th><th className="px-4 py-2">Elements</th></tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="border-t border-border">
              <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{r.id}</td>
              <td className="px-4 py-2"><StatusBadge status={r.status} /></td>
              <td className="px-4 py-2 text-xs text-muted-foreground">{new Date(r.received_at).toLocaleString()}</td>
              <td className="px-4 py-2 text-xs">
                {(r.outcomes || []).map(o => (
                  <span key={o.id} title={o.error} className="mr-1 font-mono text-muted-foreground">{o.element_index}:{o.outcome}</span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ── Endpoint detail ──────────────────────────────────────────────────────────────────────

function EndpointDetail({ endpoint, onUpdated, onBack }) {
  const [ep, setEp] = useState(endpoint);
  const [replayOffer, setReplayOffer] = useState(null);
  const url = `${window.location.origin}${ep.ingest_path}`;

  function update(data) { setEp(data); onUpdated(data); }

  async function rotate() { update((await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/rotate/`)).data); }
  async function activate() {
    try {
      const { data } = await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/activate/`);
      update(data.endpoint);
      if (data.replay_preview?.payloads > 0) setReplayOffer(data.replay_preview);
    } catch (err) { alert(err?.response?.data?.detail || 'Could not activate.'); }
  }
  async function pauseResume() {
    const resume = ep.state === 'paused';
    update((await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/pause/`, { resume })).data);
  }
  async function runReplay() {
    await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/replay/`);
    setReplayOffer(null);
  }

  return (
    <div className="p-6">
      <button type="button" onClick={onBack} className="mb-3 text-xs text-primary hover:underline">← Back to endpoints</button>
      <header className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-foreground">{ep.name}</h1>
              <span className="rounded bg-indigo-400/20 px-2 py-0.5 text-xs font-semibold text-indigo-200">{TARGET_LABELS[ep.target_type]}</span>
              <span className="text-xs text-muted-foreground">· {ep.org_name}</span>
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{url}</code>
              <button type="button" onClick={() => navigator.clipboard?.writeText(url)} className="text-xs text-primary hover:underline">copy</button>
              <button type="button" onClick={rotate} className="text-xs text-primary hover:underline" title="Regenerate = new URL">rotate</button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={ep.state} />
            {ep.state !== 'active' && (
              <button type="button" onClick={activate} className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">Activate</button>
            )}
            <button type="button" onClick={pauseResume} className="rounded-md border border-border px-3 py-1 text-xs text-muted-foreground">
              {ep.state === 'paused' ? 'Resume' : 'Pause'}
            </button>
          </div>
        </div>
        {ep.state === 'capturing' && (
          <p className="mt-3 rounded bg-background px-3 py-1.5 text-xs text-muted-foreground">
            URL is live: posts are cached &amp; 2xx&apos;d but <b className="text-foreground">no records are created</b> until you define a mapping and Activate.
          </p>
        )}
      </header>

      {replayOffer && (
        <div role="dialog" aria-label="Replay backlog" className="mt-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">
          <p>Replay {replayOffer.payloads} captured payload(s) — {replayOffer.elements_to_attempt} element(s) to process?</p>
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={runReplay} className="rounded-md bg-primary px-3 py-1 font-medium text-primary-foreground">Replay now</button>
            <button type="button" onClick={() => setReplayOffer(null)} className="rounded-md border border-border px-3 py-1 text-muted-foreground">Not now</button>
          </div>
        </div>
      )}

      <MappingBuilder endpoint={ep} onUpdated={update} />
      <CapturedPanel endpoint={ep} />
    </div>
  );
}

// ── List ─────────────────────────────────────────────────────────────────────────────────

export default function IngestEndpoints() {
  const [endpoints, setEndpoints] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');
  const [targetFilter, setTargetFilter] = useState('');

  useEffect(() => {
    api.get('/api/ingest-endpoints/endpoints/').then(({ data }) => setEndpoints(data.results || data)).catch(() => setEndpoints([]));
    api.get('/api/security/organizations/').then(({ data }) => setOrgs(data)).catch(() => setOrgs([]));
  }, []);

  const filtered = useMemo(() => endpoints.filter(e => {
    if (targetFilter && e.target_type !== targetFilter) return false;
    if (search && !e.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [endpoints, search, targetFilter]);

  function onUpdated(data) {
    setEndpoints(prev => prev.map(e => (e.id === data.id ? data : e)));
    if (selected?.id === data.id) setSelected(data);
  }

  if (selected) {
    return <EndpointDetail endpoint={selected} onUpdated={onUpdated} onBack={() => setSelected(null)} />;
  }

  return (
    <div className="p-6">
      <header className="mb-1 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Ingest Endpoints</h1>
        <button type="button" onClick={() => setCreating(true)} className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">New Endpoint</button>
      </header>
      <p className="mb-4 text-sm text-muted-foreground">Webhook intakes that map a remote system&apos;s JSON onto incidents, alerts, and assets.</p>

      {creating && (
        <CreateForm orgs={orgs}
          onSaved={data => { setCreating(false); setEndpoints(prev => [...prev, data]); setSelected(data); }}
          onCancel={() => setCreating(false)} />
      )}

      <div className="mb-3 flex flex-wrap gap-2">
        <input aria-label="Search endpoints" placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} className={INPUT} />
        <select aria-label="Target filter" value={targetFilter} onChange={e => setTargetFilter(e.target.value)} className={INPUT}>
          <option value="">All types</option>
          {Object.entries(TARGET_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Name</th><th className="px-4 py-2">Type</th><th className="px-4 py-2">Organization</th>
              <th className="px-4 py-2">State</th><th className="px-4 py-2">Captured</th><th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {filtered.map(e => (
              <tr key={e.id} className="border-t border-border">
                <td className="px-4 py-2 text-foreground">{e.name}</td>
                <td className="px-4 py-2 text-muted-foreground">{TARGET_LABELS[e.target_type]}</td>
                <td className="px-4 py-2 text-muted-foreground">{e.org_name}</td>
                <td className="px-4 py-2"><StatusBadge status={e.state} /></td>
                <td className="px-4 py-2 text-muted-foreground">{e.captured_count}</td>
                <td className="px-4 py-2 text-right">
                  <button type="button" onClick={() => setSelected(e)} className="text-xs text-primary hover:underline">Configure</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
