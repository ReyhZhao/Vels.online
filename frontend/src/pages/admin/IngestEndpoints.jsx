import { useEffect, useMemo, useState } from 'react';
import api from '@/lib/axios';

const TARGET_LABELS = { incident: 'Incident', alert: 'Alert', asset: 'Asset' };
const STATE_LABELS = { capturing: 'Capturing', active: 'Active', paused: 'Paused' };
const TARGET_FIELDS = {
  incident: ['title', 'description', 'severity', 'tlp', 'pap'],
  alert: ['title', 'description', 'severity', 'tlp', 'pap'],
  asset: ['name', 'ip_address', 'role'],
};
const ECS_FIELDS = ['host.name', 'source.ip', 'user.name', 'file.hash.sha256', 'process.name'];
const STATUSES = ['pending', 'created', 'failed', 'partial'];

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

function emptyFieldForm(fields) {
  const m = {};
  fields.forEach(f => { m[f] = { kind: 'path', path: '', value: '', value_map: '', default: '' }; });
  return m;
}
function fieldFormFromApi(fields, apiMap) {
  const m = emptyFieldForm(fields);
  Object.entries(apiMap || {}).forEach(([f, cfg]) => {
    if (!m[f]) return;
    m[f] = {
      kind: cfg.kind || 'path',
      path: cfg.path || '',
      value: cfg.value || '',
      value_map: formatValueMap(cfg.value_map),
      default: cfg.default || '',
    };
  });
  return m;
}
function fieldFormToApi(form) {
  const out = {};
  Object.entries(form).forEach(([f, cfg]) => {
    if (cfg.kind === 'constant') {
      if ((cfg.value || '').trim()) out[f] = { kind: 'constant', value: cfg.value.trim() };
    } else {
      const path = (cfg.path || '').trim();
      const value_map = parseValueMap(cfg.value_map);
      const dflt = (cfg.default || '').trim();
      if (path || Object.keys(value_map).length || dflt) {
        out[f] = { kind: 'path', path, value_map, default: dflt };
      }
    }
  });
  return out;
}

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
    <form onSubmit={submit} className="ingest-form">
      <h3>New Ingest Endpoint</h3>
      <label>Name
        <input aria-label="Endpoint name" value={name} onChange={e => setName(e.target.value)} required />
      </label>
      <label>Target type
        <select aria-label="Target type" value={targetType} onChange={e => setTargetType(e.target.value)}>
          {Object.entries(TARGET_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </label>
      <label>Organization
        <select aria-label="Target organization" value={orgId} onChange={e => setOrgId(e.target.value)}>
          {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      {error && <p role="alert" className="ingest-error">{error}</p>}
      <div className="ingest-actions">
        <button type="submit" disabled={saving}>Create</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function FieldRow({ name, cfg, onChange }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td>
        <select aria-label={`${name} kind`} value={cfg.kind} onChange={e => onChange({ ...cfg, kind: e.target.value })}>
          <option value="path">Path</option>
          <option value="constant">Constant</option>
        </select>
      </td>
      <td>
        {cfg.kind === 'constant' ? (
          <input aria-label={`${name} value`} value={cfg.value} onChange={e => onChange({ ...cfg, value: e.target.value })} placeholder="fixed value" />
        ) : (
          <input aria-label={`${name} path`} value={cfg.path} onChange={e => onChange({ ...cfg, path: e.target.value })} placeholder="result.severity" />
        )}
      </td>
      <td>
        <input aria-label={`${name} value map`} value={cfg.value_map} disabled={cfg.kind === 'constant'}
          onChange={e => onChange({ ...cfg, value_map: e.target.value })} placeholder="P1=critical, P2=high" />
      </td>
      <td>
        <input aria-label={`${name} default`} value={cfg.default} disabled={cfg.kind === 'constant'}
          onChange={e => onChange({ ...cfg, default: e.target.value })} placeholder="fallback" />
      </td>
    </tr>
  );
}

function MappingBuilder({ endpoint, onUpdated }) {
  const fields = TARGET_FIELDS[endpoint.target_type] || [];
  const [collectionRoot, setCollectionRoot] = useState(endpoint.collection_root_path || '');
  const [idemPath, setIdemPath] = useState(endpoint.idempotency_key_path || '');
  const [fieldForm, setFieldForm] = useState(fieldFormFromApi(fields, endpoint.field_mappings));
  const [entityForm, setEntityForm] = useState(fieldFormFromApi(ECS_FIELDS, endpoint.entity_mappings));
  const [samples, setSamples] = useState([]);
  const [sampleId, setSampleId] = useState('');
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    api.get(`/api/ingest-endpoints/endpoints/${endpoint.id}/captured/`)
      .then(({ data }) => setSamples(data.results || data))
      .catch(() => setSamples([]));
  }, [endpoint.id]);

  function draftConfig() {
    return {
      collection_root_path: collectionRoot,
      idempotency_key_path: idemPath,
      field_mappings: fieldFormToApi(fieldForm),
      entity_mappings: endpoint.target_type === 'alert' ? fieldFormToApi(entityForm) : {},
    };
  }

  async function save() {
    setMsg('');
    try {
      const { data } = await api.patch(`/api/ingest-endpoints/endpoints/${endpoint.id}/`, draftConfig());
      onUpdated(data);
      setMsg('Mapping saved.');
    } catch { setMsg('Could not save mapping.'); }
  }

  async function runPreview() {
    if (!sampleId) return;
    try {
      const { data } = await api.post(`/api/ingest-endpoints/endpoints/${endpoint.id}/dry-run/`, {
        ...draftConfig(), captured_payload: sampleId,
      });
      setPreview(data.elements);
    } catch { setPreview(null); }
  }

  return (
    <section className="ingest-builder" aria-label="Mapping builder">
      <h4>Field mapping</h4>
      <label>Collection root (array to fan out)
        <input aria-label="Collection root path" value={collectionRoot} onChange={e => setCollectionRoot(e.target.value)} placeholder="results" />
      </label>
      <label>Idempotency key path
        <input aria-label="Idempotency key path" value={idemPath} onChange={e => setIdemPath(e.target.value)} placeholder="event_id" />
      </label>
      <table>
        <thead><tr><th>Field</th><th>Kind</th><th>Path / value</th><th>Value map</th><th>Default</th></tr></thead>
        <tbody>
          {fields.map(f => (
            <FieldRow key={f} name={f} cfg={fieldForm[f]}
              onChange={cfg => setFieldForm(prev => ({ ...prev, [f]: cfg }))} />
          ))}
        </tbody>
      </table>

      {endpoint.target_type === 'alert' && (
        <>
          <h4>ECS entity mapping <span className="hint">(at least one required to activate)</span></h4>
          <table>
            <thead><tr><th>Entity</th><th>Kind</th><th>Path / value</th><th>Value map</th><th>Default</th></tr></thead>
            <tbody>
              {ECS_FIELDS.map(f => (
                <FieldRow key={f} name={f} cfg={entityForm[f]}
                  onChange={cfg => setEntityForm(prev => ({ ...prev, [f]: cfg }))} />
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="ingest-preview">
        <label>Preview against sample
          <select aria-label="Preview sample" value={sampleId} onChange={e => setSampleId(e.target.value)}>
            <option value="">— pick a captured payload —</option>
            {samples.map(s => <option key={s.id} value={s.id}>#{s.id} · {s.status}</option>)}
          </select>
        </label>
        <button type="button" onClick={runPreview} disabled={!sampleId}>Dry-run preview</button>
        {preview && (
          <pre aria-label="Dry-run result">{JSON.stringify(preview, null, 2)}</pre>
        )}
      </div>

      {msg && <p role="status">{msg}</p>}
      <button type="button" onClick={save}>Save mapping</button>
    </section>
  );
}

function CapturedPanel({ endpoint }) {
  const [statusFilter, setStatusFilter] = useState('');
  const [rows, setRows] = useState([]);

  function load() {
    const q = statusFilter ? `?status=${statusFilter}` : '';
    api.get(`/api/ingest-endpoints/endpoints/${endpoint.id}/captured/${q}`)
      .then(({ data }) => setRows(data.results || data))
      .catch(() => setRows([]));
  }
  useEffect(load, [endpoint.id, statusFilter]);

  return (
    <section className="ingest-captured" aria-label="Captured payloads">
      <h4>Captured payloads</h4>
      <label>Status
        <select aria-label="Status filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <table>
        <thead><tr><th>#</th><th>Status</th><th>Received</th><th>Elements</th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.status}</td>
              <td>{new Date(r.received_at).toLocaleString()}</td>
              <td>
                {(r.outcomes || []).map(o => (
                  <span key={o.id} title={o.error} className={`outcome outcome-${o.outcome}`}>
                    {o.element_index}:{o.outcome}{' '}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function EndpointDetail({ endpoint, onUpdated, onBack }) {
  const [ep, setEp] = useState(endpoint);
  const [replayOffer, setReplayOffer] = useState(null);
  const url = `${window.location.origin}${ep.ingest_path}`;

  function update(data) { setEp(data); onUpdated(data); }

  async function rotate() {
    const { data } = await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/rotate/`);
    update(data);
  }
  async function activate() {
    try {
      const { data } = await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/activate/`);
      update(data.endpoint);
      if (data.replay_preview?.payloads > 0) setReplayOffer(data.replay_preview);
    } catch (err) { alert(err?.response?.data?.detail || 'Could not activate.'); }
  }
  async function pauseResume() {
    const resume = ep.state === 'paused';
    const { data } = await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/pause/`, { resume });
    update(data);
  }
  async function runReplay() {
    await api.post(`/api/ingest-endpoints/endpoints/${ep.id}/replay/`);
    setReplayOffer(null);
  }

  return (
    <div className="ingest-detail">
      <button type="button" onClick={onBack}>← Back</button>
      <h2>{ep.name} <span className={`state state-${ep.state}`}>{STATE_LABELS[ep.state]}</span></h2>
      <p className="ingest-meta">{TARGET_LABELS[ep.target_type]} → {ep.org_name}</p>
      <div className="ingest-url">
        <code>{url}</code>
        <button type="button" onClick={() => navigator.clipboard?.writeText(url)}>Copy</button>
        <button type="button" onClick={rotate}>Rotate URL</button>
      </div>
      <div className="ingest-lifecycle">
        {ep.state !== 'active' && <button type="button" onClick={activate}>Activate</button>}
        <button type="button" onClick={pauseResume}>{ep.state === 'paused' ? 'Resume' : 'Pause'}</button>
      </div>

      {replayOffer && (
        <div className="ingest-replay-offer" role="dialog" aria-label="Replay backlog">
          <p>Replay {replayOffer.payloads} captured payload(s) — {replayOffer.elements_to_attempt} element(s) to process?</p>
          <button type="button" onClick={runReplay}>Replay now</button>
          <button type="button" onClick={() => setReplayOffer(null)}>Not now</button>
        </div>
      )}

      <MappingBuilder endpoint={ep} onUpdated={update} />
      <CapturedPanel endpoint={ep} />
    </div>
  );
}

export default function IngestEndpoints() {
  const [endpoints, setEndpoints] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');
  const [targetFilter, setTargetFilter] = useState('');

  function load() {
    api.get('/api/ingest-endpoints/endpoints/')
      .then(({ data }) => setEndpoints(data.results || data))
      .catch(() => setEndpoints([]));
  }
  useEffect(() => {
    load();
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
    <div className="ingest-endpoints">
      <header className="ingest-header">
        <h1>Ingest Endpoints</h1>
        <button type="button" onClick={() => setCreating(true)}>New Endpoint</button>
      </header>
      <p className="ingest-intro">Webhook intakes that map a remote system's JSON onto incidents, alerts, and assets.</p>

      {creating && (
        <CreateForm orgs={orgs}
          onSaved={data => { setCreating(false); setEndpoints(prev => [...prev, data]); setSelected(data); }}
          onCancel={() => setCreating(false)} />
      )}

      <div className="ingest-filters">
        <input aria-label="Search endpoints" placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
        <select aria-label="Target filter" value={targetFilter} onChange={e => setTargetFilter(e.target.value)}>
          <option value="">All types</option>
          {Object.entries(TARGET_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <table>
        <thead><tr><th>Name</th><th>Type</th><th>Organization</th><th>State</th><th>Captured</th><th></th></tr></thead>
        <tbody>
          {filtered.map(e => (
            <tr key={e.id}>
              <td>{e.name}</td>
              <td>{TARGET_LABELS[e.target_type]}</td>
              <td>{e.org_name}</td>
              <td><span className={`state state-${e.state}`}>{STATE_LABELS[e.state]}</span></td>
              <td>{e.captured_count}</td>
              <td><button type="button" onClick={() => setSelected(e)}>Configure</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
